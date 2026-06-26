"""Serial device discovery and IO."""

from __future__ import annotations

from dataclasses import dataclass
import glob
import platform
import time
from pathlib import Path

import serial
import serial.tools.list_ports


BAUDRATE = 115200
RP2040_VID = "2e8a"
RP2040_PID = "0005"


@dataclass(frozen=True)
class SerialCandidate:
    port: str
    matched_vid_pid: bool = False


def list_candidates() -> list[SerialCandidate]:
    system = platform.system()
    if system == "Windows":
        return _list_port_candidates()
    if system == "Linux":
        return _linux_candidates()
    return _list_port_candidates()


def autodetect_port(require_ping: bool = True) -> str | None:
    candidates = list_candidates()
    preferred = [item for item in candidates if item.matched_vid_pid]
    fallback = [item for item in candidates if not item.matched_vid_pid]

    for candidate in [*preferred, *fallback]:
        if not require_ping or ping_port(candidate.port):
            return candidate.port
    return None


def open_serial(port: str | None = None, timeout: float = 1.0) -> serial.Serial:
    selected = port or autodetect_port()
    if selected is None:
        raise serial.SerialException("No RaspDeck device found")
    return serial.Serial(selected, BAUDRATE, timeout=timeout)


def ping_port(port: str, timeout: float = 2.0, settle: float = 1.5) -> bool:
    try:
        with serial.Serial(port=port, baudrate=BAUDRATE, timeout=timeout) as connection:
            time.sleep(settle)
            connection.reset_input_buffer()
            connection.write(b"ping\n")
            response = connection.readline().decode(errors="replace").strip()
            return response.lower() == "pong"
    except (OSError, serial.SerialException):
        return False


def _linux_candidates() -> list[SerialCandidate]:
    candidates: list[SerialCandidate] = []
    seen: set[str] = set()

    for tty in sorted(glob.glob("/sys/class/tty/ttyACM*")):
        uevent = Path(tty) / "device" / "uevent"
        if not uevent.exists():
            continue
        text = uevent.read_text(errors="ignore").lower()
        if RP2040_VID in text and RP2040_PID in text:
            port = "/dev/" + Path(tty).name
            candidates.append(SerialCandidate(port, matched_vid_pid=True))
            seen.add(port)

    for port in sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")):
        if port not in seen:
            candidates.append(SerialCandidate(port))
            seen.add(port)

    return candidates


def _list_port_candidates() -> list[SerialCandidate]:
    candidates: list[SerialCandidate] = []
    for port in serial.tools.list_ports.comports():
        vid = f"{port.vid:04x}" if port.vid is not None else ""
        pid = f"{port.pid:04x}" if port.pid is not None else ""
        candidates.append(SerialCandidate(port.device, vid == RP2040_VID and pid == RP2040_PID))
    return candidates
