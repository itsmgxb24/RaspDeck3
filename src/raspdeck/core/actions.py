"""Action dispatching."""

from __future__ import annotations

from dataclasses import dataclass
import shlex
import shutil
import subprocess
import threading

from raspdeck.core.display import Display, DisplayRunner


DEFAULT_VOLUME_STEP = 5


@dataclass
class ActionContext:
    display: Display
    display_runner: DisplayRunner
    display_blocks: dict[str, dict[str, object]]
    audio: "AudioController"
    player: "PlayerController"


class AudioController:
    def volume_up(self, step: int = DEFAULT_VOLUME_STEP) -> None:
        if shutil.which("pactl"):
            _run_quiet(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step}%"])
        elif shutil.which("wpctl"):
            _run_quiet(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{step}%+"])

    def volume_down(self, step: int = DEFAULT_VOLUME_STEP) -> None:
        if shutil.which("pactl"):
            _run_quiet(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step}%"])
        elif shutil.which("wpctl"):
            _run_quiet(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{step}%-"])

    def mute(self) -> None:
        if shutil.which("pactl"):
            _run_quiet(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        elif shutil.which("wpctl"):
            _run_quiet(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])

    def volume_percent(self) -> int:
        if shutil.which("pactl"):
            return _pactl_volume_percent()
        if shutil.which("wpctl"):
            return _wpctl_volume_percent()
        return -1


class PlayerController:
    def status(self) -> str:
        if not shutil.which("playerctl"):
            return ""
        result = subprocess.run(
            ["playerctl", "status"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def command(self, name: str) -> bool:
        if not shutil.which("playerctl"):
            return False
        result = subprocess.run(
            ["playerctl", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0


class ConditionState:
    def __init__(self) -> None:
        self.last_volume = -1


def dispatch(action: str, context: ActionContext) -> None:
    action = action.strip()
    if not action:
        return

    if action.startswith("exec="):
        subprocess.Popen(action[5:].strip(), shell=True)
    elif action.startswith("print="):
        _type_text(action[6:])
    elif action.startswith("log="):
        print(f"[log] {action[4:]}")
    elif action.startswith("volume_up"):
        context.audio.volume_up(_parse_action_arg(action, DEFAULT_VOLUME_STEP))
    elif action.startswith("volume_down"):
        context.audio.volume_down(_parse_action_arg(action, DEFAULT_VOLUME_STEP))
    elif action == "volume_mute":
        context.audio.mute()
    elif action in {"media_play_pause", "media_next", "media_prev", "media_stop"}:
        _media_action(action, context.player)
    elif action.startswith("trigger "):
        _dispatch_trigger(action[8:].strip(), context)
    elif action.startswith("serial="):
        context.display.send(action[7:].strip())
    else:
        print(f"[actions] unknown action: {action!r}")


def evaluate_condition(condition: str, context: ActionContext, state: ConditionState) -> bool:
    lower = condition.lower()
    if lower.startswith("playerctl."):
        expected = condition[10:].strip().lower()
        return context.player.status().lower() == expected
    if lower.startswith("volume(") and lower.endswith(")"):
        current = context.audio.volume_percent()
        if current != state.last_volume:
            state.last_volume = current
            return True
        return False
    print(f"[actions] unknown condition: {condition!r}")
    return False


def _dispatch_trigger(call: str, context: ActionContext) -> None:
    if "(" in call and call.endswith(")"):
        name = call[: call.index("(")].strip()
        args_text = call[call.index("(") + 1 : -1]
        args = [arg.strip() for arg in args_text.split(",") if arg.strip()]
    else:
        name = call.strip()
        args = []

    block = context.display_blocks.get(name)
    if block is None:
        print(f"[trigger] unknown display block: {name!r}")
        return

    threading.Thread(
        target=context.display_runner.run_block,
        args=(block, args, f"display:{name}"),
        daemon=True,
    ).start()


def _media_action(action: str, player: PlayerController) -> None:
    mapping = {
        "media_play_pause": "play-pause",
        "media_next": "next",
        "media_prev": "previous",
        "media_stop": "stop",
    }
    if player.command(mapping[action]):
        return
    _send_media_key(action)


def _send_media_key(action: str) -> None:
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        print("[actions] pynput is not installed")
        return

    key_map = {
        "media_play_pause": getattr(Key, "media_play_pause", None),
        "media_next": getattr(Key, "media_next", None),
        "media_prev": getattr(Key, "media_previous", None),
        "media_stop": getattr(Key, "media_stop", None),
    }
    key = key_map.get(action)
    if key is None:
        print(f"[actions] media key is unavailable: {action}")
        return

    keyboard = Controller()
    keyboard.press(key)
    keyboard.release(key)


def _type_text(text: str) -> None:
    try:
        from pynput.keyboard import Controller
    except ImportError:
        print("[actions] pynput is not installed")
        return
    Controller().type(text)


def _parse_action_arg(action: str, default: int) -> int:
    if "(" not in action or not action.endswith(")"):
        return default
    try:
        return int(action[action.index("(") + 1 : -1].strip())
    except ValueError:
        return default


def _pactl_volume_percent() -> int:
    result = subprocess.run(
        ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return -1
    for part in result.stdout.split():
        if part.endswith("%"):
            return int(part.rstrip("%"))
    return -1


def _wpctl_volume_percent() -> int:
    result = subprocess.run(
        ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return -1
    parts = shlex.split(result.stdout)
    for part in parts:
        try:
            return round(float(part) * 100)
        except ValueError:
            continue
    return -1


def _run_quiet(command: list[str]) -> None:
    subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
