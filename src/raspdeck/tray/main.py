"""System tray entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading

import serial

from raspdeck.core.serial_device import BAUDRATE, autodetect_port


ICON_PATH = Path.home() / ".config" / "raspdeck" / "tray.png"
Image = None
ImageDraw = None
pystray = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="raspdeck-tray")
    parser.add_argument("--port", help="Serial port path")
    args = parser.parse_args(argv)
    _load_tray_deps()
    RaspDeckTray(args.port).run()
    return 0


def _load_tray_deps() -> None:
    global Image, ImageDraw, pystray
    from PIL import Image as image_module
    from PIL import ImageDraw as image_draw_module
    import pystray as pystray_module

    Image = image_module
    ImageDraw = image_draw_module
    pystray = pystray_module


class RaspDeckTray:
    def __init__(self, port: str | None = None):
        self._requested_port = port
        self._serial: serial.Serial | None = None
        self._port: str | None = None
        self._lock = threading.Lock()

        self._connect()
        self._icon = pystray.Icon(
            "raspdeck",
            _make_icon_image(self._serial is not None),
            self._tooltip(),
            pystray.Menu(
                pystray.MenuItem("Send command...", self._open_send_window),
                pystray.MenuItem("Reconnect", self._reconnect),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def run(self) -> None:
        self._icon.run()

    def _connect(self) -> None:
        self._port = self._requested_port or autodetect_port()
        if self._port is None:
            self._serial = None
            return
        try:
            self._serial = serial.Serial(self._port, BAUDRATE, timeout=1)
        except serial.SerialException:
            self._serial = None
            self._port = None

    def _send(self, command: str) -> bool:
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                return False
            try:
                self._serial.write((command.strip() + "\n").encode())
                return True
            except serial.SerialException:
                self._serial = None
                self._port = None
                self._update_icon()
                return False

    def _reconnect(self, _icon=None, _item=None) -> None:
        with self._lock:
            if self._serial is not None:
                self._serial.close()
            self._connect()
        self._update_icon()

    def _open_send_window(self, _icon=None, _item=None) -> None:
        threading.Thread(target=self._send_window, daemon=True).start()

    def _send_window(self) -> None:
        import tkinter as tk

        window = tk.Tk()
        window.title("RaspDeck")
        window.resizable(False, False)
        window.attributes("-topmost", True)

        tk.Label(window, text="Command:", padx=10, pady=6).grid(row=0, column=0, sticky="e")
        entry = tk.Entry(window, width=32)
        entry.grid(row=0, column=1, padx=(0, 10), pady=10)
        entry.focus()
        status = tk.Label(window, text="", fg="gray", padx=10)
        status.grid(row=1, column=0, columnspan=3, pady=(0, 4))

        def send(_event=None) -> None:
            command = entry.get().strip()
            if not command:
                return
            if self._send(command):
                status.config(text=f"Sent: {command}", fg="green")
                entry.delete(0, tk.END)
            else:
                status.config(text="Not connected", fg="red")

        tk.Button(window, text="Send", command=send, width=8).grid(row=0, column=2, padx=(0, 10))
        window.bind("<Return>", send)
        window.mainloop()

    def _quit(self, _icon=None, _item=None) -> None:
        with self._lock:
            if self._serial is not None:
                self._serial.close()
        self._icon.stop()

    def _update_icon(self) -> None:
        connected = self._serial is not None
        self._icon.icon = _make_icon_image(connected)
        self._icon.title = self._tooltip()

    def _tooltip(self) -> str:
        return f"RaspDeck ({self._port})" if self._port else "RaspDeck (not connected)"


def _make_icon_image(connected: bool) -> Image.Image:
    if Image is None or ImageDraw is None:
        raise RuntimeError("tray image dependencies are not loaded")

    if ICON_PATH.exists():
        image = Image.open(ICON_PATH).convert("RGBA")
        if connected:
            return image
        red, green, blue, alpha = image.split()
        gray = image.convert("L")
        return Image.merge("RGBA", (gray, gray, gray, alpha))

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = (80, 200, 120) if connected else (180, 180, 180)
    draw.rounded_rectangle([4, 4, 60, 60], radius=10, fill=color)
    for row in range(3):
        for col in range(3):
            x = 18 + col * 14
            y = 18 + row * 14
            draw.ellipse([x, y, x + 6, y + 6], fill=(20, 20, 20))
    return image


if __name__ == "__main__":
    raise SystemExit(main())
