"""Display protocol helpers."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import serial


VolumeReader = Callable[[], int]


class Display:
    def __init__(self, port: serial.Serial):
        self._port = port
        self._lock = threading.Lock()
        self._buffer = [0] * 64
        self._layers: dict[str, list[int]] = {}

    def send(self, message: str) -> None:
        with self._lock:
            self._port.write((message.strip() + "\n").encode())

    def activate_layer(self, key: str, pixels: list[int]) -> None:
        if len(pixels) != 64:
            raise ValueError("display layer must contain 64 pixels")
        self._layers[key] = [1 if value else 0 for value in pixels]
        self._rebuild()

    def deactivate_layer(self, key: str) -> None:
        if key in self._layers:
            del self._layers[key]
            self._rebuild()

    def clear(self) -> None:
        self._layers.clear()
        self._buffer = [0] * 64
        self.send("clear")

    def brightness(self, level: int) -> None:
        self.send(f"bright {max(0, min(15, level))}")

    def led_color(self, color: str) -> None:
        self.send(f"led -c {color}")

    def led_brightness(self, percent: int) -> None:
        self.send(f"led -b {max(0, min(100, percent))}")

    def _rebuild(self) -> None:
        merged = [0] * 64
        for layer in self._layers.values():
            for index, value in enumerate(layer):
                if value:
                    merged[index] = 1
        self._buffer = merged
        self.send("pixels " + "".join(str(bit) for bit in self._buffer))


class DisplayRunner:
    def __init__(self, display: Display, read_volume: VolumeReader):
        self._display = display
        self._read_volume = read_volume
        self._fade_cancels: dict[str, threading.Event] = {}
        self._fade_lock = threading.Lock()

    def run_block(self, block: dict[str, object], args: list[str], layer_key: str) -> None:
        args_lower = [arg.lower() for arg in args]
        for if_block in block.get("if_blocks", []):
            if not isinstance(if_block, dict):
                continue
            if str(if_block.get("arg", "")).lower() in args_lower:
                for command in if_block.get("commands", []):
                    self.exec_command(str(command), layer_key)
        tail = [str(command) for command in block.get("tail", [])]
        self.exec_tail(tail, layer_key)

    def exec_tail(self, commands: list[str], layer_key: str) -> None:
        index = 0
        while index < len(commands):
            command = commands[index].strip()
            index += 1
            if command.lower().startswith("wait "):
                try:
                    delay_ms = int(command.split()[1])
                except (IndexError, ValueError):
                    continue
                remaining = commands[index:]
                threading.Thread(
                    target=self._continue_tail,
                    args=(delay_ms, remaining, layer_key),
                    daemon=True,
                ).start()
                return
            self.exec_command(command, layer_key)

    def exec_command(self, command: str, layer_key: str) -> None:
        lower = command.lower()
        if lower == "clear":
            self._display.deactivate_layer(layer_key)
        elif lower.startswith("bright "):
            self._exec_brightness(command)
        elif lower.startswith("pixels "):
            self._exec_pixels(command, layer_key)
        elif lower.startswith("volume."):
            self._exec_volume(command, layer_key)
        else:
            print(f"[display] unknown command: {command!r}")

    def _continue_tail(self, delay_ms: int, commands: list[str], layer_key: str) -> None:
        time.sleep(delay_ms / 1000)
        self.exec_tail(commands, layer_key)

    def _exec_brightness(self, command: str) -> None:
        try:
            self._display.brightness(int(command.split()[1]))
        except (IndexError, ValueError):
            print(f"[display] invalid brightness command: {command!r}")

    def _exec_pixels(self, command: str, layer_key: str) -> None:
        pixels = parse_pixels_arg(command[7:].strip())
        if pixels is None:
            print(f"[display] invalid pixels command: {command!r}")
            return
        self._display.activate_layer(layer_key, pixels)

    def _exec_volume(self, command: str, layer_key: str) -> None:
        mode, limit = parse_volume_cmd(command)
        pixels = volume_pixels(mode, limit, self._read_volume())
        volume_key = layer_key + ":volume"
        self._display.activate_layer(volume_key, pixels)

        with self._fade_lock:
            old_cancel = self._fade_cancels.get(volume_key)
            if old_cancel is not None:
                old_cancel.set()
            cancel = threading.Event()
            self._fade_cancels[volume_key] = cancel

        threading.Thread(target=self._fade_volume, args=(volume_key, cancel), daemon=True).start()

    def _fade_volume(self, layer_key: str, cancel: threading.Event) -> None:
        time.sleep(1)
        if cancel.is_set():
            return
        self._display.deactivate_layer(layer_key)
        with self._fade_lock:
            if self._fade_cancels.get(layer_key) is cancel:
                del self._fade_cancels[layer_key]


def parse_pixels_arg(value: str) -> list[int] | None:
    if value.startswith("-h ") or value.startswith("--human-readable "):
        index_text = value.split(" ", 1)[1].strip()
        pixels = [0] * 64
        for token in index_text.split(","):
            token = token.strip()
            if not token.isdigit():
                continue
            index = int(token)
            if 0 <= index <= 63:
                pixels[index] = 1
        return pixels

    if len(value) >= 64 and all(char in "01" for char in value[:64]):
        return [int(char) for char in value[:64]]
    return None


def parse_volume_cmd(command: str) -> tuple[str, int]:
    rest = command[7:]
    if "(" in rest and rest.endswith(")"):
        mode = rest[: rest.index("(")].strip()
        try:
            limit = int(rest[rest.index("(") + 1 : -1].strip())
        except ValueError:
            limit = 8
    else:
        mode = rest.strip()
        limit = 8
    return mode, max(0, min(8, limit))


def volume_pixels(mode: str, limit: int, percent: int) -> list[int]:
    pixels = [0] * 64
    if limit == 0 or percent < 0:
        return pixels
    percent = max(0, min(100, percent))

    if mode == "vertical_top":
        return _linear_pixels(limit * 8, percent, lambda index: index)
    if mode == "vertical_bottom":
        return _linear_pixels(limit * 8, percent, lambda index: (7 - index // 8) * 8 + index % 8)
    if mode == "horizontal_left":
        return _linear_pixels(limit * 8, percent, lambda index: (index % 8) * 8 + index // 8)
    if mode == "horizontal_right":
        return _linear_pixels(limit * 8, percent, lambda index: (index % 8) * 8 + (7 - index // 8))
    if mode == "diagonal_fromRightTop":
        order = []
        for diagonal in range(15):
            for row in range(8):
                col = 7 - (diagonal - row)
                if 0 <= col <= 7:
                    order.append(row * 8 + col)
        filled = round(percent / 100 * len(order))
        for index in order[:filled]:
            pixels[index] = 1
        return pixels

    print(f"[display] unknown VOLUME mode: {mode!r}")
    return pixels


def _linear_pixels(max_pixels: int, percent: int, mapper: Callable[[int], int]) -> list[int]:
    pixels = [0] * 64
    filled = round(percent / 100 * max_pixels)
    for index in range(filled):
        pixels[mapper(index)] = 1
    return pixels
