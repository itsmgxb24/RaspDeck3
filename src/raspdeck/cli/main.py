"""Command line entrypoint."""

from __future__ import annotations

import argparse
import sys
import time

import serial

from raspdeck.core.config import ensure_config
from raspdeck.core.serial_device import BAUDRATE, autodetect_port, list_candidates, open_serial, ping_port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rd-tool")
    parser.add_argument("-a", "--auto-detect", action="store_true", help="Find the RaspDeck serial port")
    parser.add_argument("-t", "--test-connection", action="store_true", help="Test the RaspDeck connection")
    parser.add_argument("-m", "--matrixify", action="store_true", help="Open the matrix editor")
    parser.add_argument("--init-config", action="store_true", help="Create the default config")
    parser.add_argument("--send", metavar="COMMAND", help="Send one command to the device")
    parser.add_argument("--port", help="Serial port path")
    args = parser.parse_args(argv)

    if args.auto_detect:
        return _auto_detect()
    if args.test_connection:
        return _test_connection(args.port)
    if args.matrixify:
        return _matrixify()
    if args.init_config:
        path = ensure_config()
        print(path)
        return 0
    if args.send:
        return _send(args.send, args.port)

    parser.print_help()
    return 0


def _auto_detect() -> int:
    candidates = list_candidates()
    if not candidates:
        print("No serial ports found.")
        return 1

    print("Scanning:")
    for candidate in candidates:
        label = "vid/pid" if candidate.matched_vid_pid else "serial"
        print(f"  {candidate.port} ({label})")

    port = autodetect_port()
    if port is None:
        print("RaspDeck not found.")
        return 1

    print(f"RaspDeck detected on: {port}")
    return 0


def _test_connection(port: str | None) -> int:
    selected = port or autodetect_port()
    if selected is None:
        print("RaspDeck not found.")
        return 1
    if not ping_port(selected):
        print(f"No pong from {selected}.")
        return 1
    print(f"Connection OK: {selected}")
    return 0


def _send(command: str, port: str | None) -> int:
    try:
        with open_serial(port) as connection:
            time.sleep(0.5)
            connection.write((command.strip() + "\n").encode())
    except serial.SerialException as exc:
        print(f"Could not send command: {exc}", file=sys.stderr)
        return 1
    return 0


def _matrixify() -> int:
    try:
        import tkinter as tk
    except ImportError:
        print("tkinter is required for matrixify", file=sys.stderr)
        return 1

    selected: set[int] = set()
    serial_port: serial.Serial | None = None

    root = tk.Tk()
    root.title("matrixify")

    serial_label = tk.Label(root, text="serial: searching", bg="#cccccc", anchor="w", padx=8, pady=6)
    serial_label.pack(fill="x", padx=5, pady=(5, 0))

    canvas = tk.Canvas(root, width=370, height=370, bg="white", highlightthickness=0)
    canvas.pack(padx=5, pady=5)

    bottom = tk.Frame(root)
    bottom.pack(fill="x", padx=5, pady=(0, 5))
    info = tk.Label(bottom, text="", bg="#dddddd", anchor="w", padx=8, pady=6)
    info.pack(side="left", fill="x", expand=True)

    rectangles: dict[int, int] = {}
    for row in range(8):
        for col in range(8):
            number = row * 8 + col
            x1 = 5 + col * 45
            y1 = 5 + row * 45
            rectangles[number] = canvas.create_rectangle(x1, y1, x1 + 45, y1 + 45, fill="white")
            canvas.create_text(x1 + 22, y1 + 22, text=str(number))

    def update_text() -> None:
        info.config(text=",".join(str(number) for number in sorted(selected)))

    def set_pixel(number: int, enabled: bool) -> None:
        if enabled:
            selected.add(number)
            canvas.itemconfig(rectangles[number], fill="red")
        else:
            selected.discard(number)
            canvas.itemconfig(rectangles[number], fill="white")
        update_text()

    def click(event, enabled: bool) -> None:
        col = (event.x - 5) // 45
        row = (event.y - 5) // 45
        if 0 <= row < 8 and 0 <= col < 8:
            set_pixel(row * 8 + col, enabled)

    def connect() -> None:
        nonlocal serial_port
        port = autodetect_port()
        if port is None:
            serial_label.config(text="serial: no device")
            return
        try:
            serial_port = serial.Serial(port, BAUDRATE, timeout=1)
        except serial.SerialException as exc:
            serial_label.config(text=f"serial: {exc}")
            return
        serial_label.config(text=f"serial: {port}")

    def send() -> None:
        if serial_port is None:
            info.config(text="No connection.")
            return
        text = ",".join(str(number) for number in sorted(selected))
        serial_port.write(f"pixels -h {text}\n".encode())
        info.config(text=f"Sent: {text}")

    def copy() -> None:
        root.clipboard_clear()
        root.clipboard_append(info.cget("text"))

    canvas.bind("<Button-1>", lambda event: click(event, True))
    canvas.bind("<Button-3>", lambda event: click(event, False))
    tk.Button(bottom, text="Send", command=send).pack(side="left", padx=(5, 0))
    tk.Button(bottom, text="Copy", command=copy).pack(side="left", padx=(5, 0))
    root.after(100, connect)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
