"""Daemon entrypoint."""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time

import serial

from raspdeck.core.actions import (
    ActionContext,
    AudioController,
    ConditionState,
    PlayerController,
    dispatch,
    evaluate_condition,
)
from raspdeck.core.config import ConfigError, load_config
from raspdeck.core.display import Display, DisplayRunner
from raspdeck.core.notifications import notification_matches, start_notification_watcher
from raspdeck.core.serial_device import open_serial


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="raspdeck-daemon")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--port", help="Serial port path")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    port = args.port or config.settings.get("PORT")
    try:
        serial_port = open_serial(port)
    except serial.SerialException as exc:
        print(f"Could not open RaspDeck serial port: {exc}", file=sys.stderr)
        return 1

    time.sleep(0.5)
    display = Display(serial_port)
    audio = AudioController()
    display_runner = DisplayRunner(display, audio.volume_percent)
    context = ActionContext(
        display=display,
        display_runner=display_runner,
        display_blocks=config.display_blocks,
        audio=audio,
        player=PlayerController(),
    )
    condition_state = ConditionState()

    _apply_startup_settings(config.settings, display)

    event_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
    notif_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    threading.Thread(target=_reader_thread, args=(serial_port, event_queue), daemon=True).start()

    if config.notif_rules:
        start_notification_watcher(notif_queue)

    bindings = _collect_bindings(config.action_rules)
    condition_rules = [rule for rule in config.action_rules if rule.get("type") == "if"]
    _start_trigger_threads(config.triggers, config.display_blocks, condition_rules, context, condition_state)

    print(f"RaspDeck connected on {serial_port.port}.")
    print(f"Config: {config.path}")

    try:
        _event_loop(event_queue, notif_queue, bindings, condition_rules, config.notif_rules, context, condition_state)
    except KeyboardInterrupt:
        print("\nQuitting.")
    finally:
        display.clear()
        serial_port.close()
    return 0


def _apply_startup_settings(settings: dict[str, str], display: Display) -> None:
    try:
        display.brightness(int(settings.get("BRIGHT", 8)))
    except ValueError:
        print("[config] invalid BRIGHT value")

    display.clear()
    if "LED_COLOR" in settings:
        display.led_color(settings["LED_COLOR"])
    if "LED_BRIGHT" in settings:
        try:
            display.led_brightness(int(settings["LED_BRIGHT"]))
        except ValueError:
            print("[config] invalid LED_BRIGHT value")


def _reader_thread(serial_port: serial.Serial, event_queue: queue.Queue[tuple[str, str | None]]) -> None:
    while True:
        try:
            line = serial_port.readline().decode(errors="replace").strip()
        except serial.SerialException:
            event_queue.put(("quit", None))
            return
        except OSError as exc:
            print(f"[serial] read error: {exc}")
            time.sleep(0.1)
            continue

        if line:
            event_queue.put(("serial", line))


def _collect_bindings(action_rules: list[dict[str, object]]) -> dict[str, list[str]]:
    bindings: dict[str, list[str]] = {}
    for rule in action_rules:
        if rule.get("type") != "binding":
            continue
        event = str(rule.get("event", ""))
        action = str(rule.get("action", ""))
        if event and action:
            bindings.setdefault(event, []).append(action)
    return bindings


def _start_trigger_threads(
    triggers: dict[str, int | None],
    display_blocks: dict[str, dict[str, object]],
    condition_rules: list[dict[str, object]],
    context: ActionContext,
    condition_state: ConditionState,
) -> None:
    for name, interval_ms in triggers.items():
        if interval_ms is None:
            continue
        if name == "VOLUME":
            threading.Thread(
                target=_volume_poll,
                args=(interval_ms, condition_rules, context, condition_state),
                daemon=True,
            ).start()
            continue

        block = display_blocks.get(name)
        if block is not None:
            threading.Thread(
                target=_display_poll,
                args=(interval_ms, name, block, context.display_runner),
                daemon=True,
            ).start()


def _volume_poll(
    interval_ms: int,
    condition_rules: list[dict[str, object]],
    context: ActionContext,
    condition_state: ConditionState,
) -> None:
    while True:
        time.sleep(interval_ms / 1000)
        for rule in condition_rules:
            condition = str(rule.get("condition", ""))
            if not condition.lower().startswith("volume("):
                continue
            if evaluate_condition(condition, context, condition_state):
                for action in rule.get("body", []):
                    dispatch(str(action), context)


def _display_poll(
    interval_ms: int,
    name: str,
    block: dict[str, object],
    display_runner: DisplayRunner,
) -> None:
    while True:
        time.sleep(interval_ms / 1000)
        display_runner.run_block(block, [], f"display:{name}")


def _event_loop(
    event_queue: queue.Queue[tuple[str, str | None]],
    notif_queue: queue.Queue[tuple[str, str]],
    bindings: dict[str, list[str]],
    condition_rules: list[dict[str, object]],
    notif_rules: list[dict[str, object]],
    context: ActionContext,
    condition_state: ConditionState,
) -> None:
    while True:
        _drain_notifications(notif_queue, notif_rules, context)

        try:
            kind, data = event_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        if kind == "quit":
            return
        if kind == "serial" and data is not None:
            _handle_serial_event(data, bindings, condition_rules, context, condition_state)


def _drain_notifications(
    notif_queue: queue.Queue[tuple[str, str]],
    notif_rules: list[dict[str, object]],
    context: ActionContext,
) -> None:
    while True:
        try:
            app_name, text = notif_queue.get_nowait()
        except queue.Empty:
            return

        for rule in notif_rules:
            if notification_matches(rule, app_name, text):
                for action in rule.get("body", []):
                    dispatch(str(action), context)


def _handle_serial_event(
    event: str,
    bindings: dict[str, list[str]],
    condition_rules: list[dict[str, object]],
    context: ActionContext,
    condition_state: ConditionState,
) -> None:
    actions = bindings.get(event, [])
    if actions:
        for action in actions:
            dispatch(action, context)
    else:
        print(f"Unbound event: {event}")

    for rule in condition_rules:
        condition = str(rule.get("condition", ""))
        if evaluate_condition(condition, context, condition_state):
            for action in rule.get("body", []):
                dispatch(str(action), context)


if __name__ == "__main__":
    raise SystemExit(main())
