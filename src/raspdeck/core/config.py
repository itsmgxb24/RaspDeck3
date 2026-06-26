"""Config loading and parsing."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


APP_NAME = "raspdeck"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.conf"

DEFAULT_CONFIG = """\
# RaspDeck3 config

BRIGHT = 8
LED_COLOR = FF0000
LED_BRIGHT = 10
# PORT = /dev/ttyACM0

ACTIONS
    ENC:+1 = volume_up(2)
    ENC:-1 = volume_down(2)
    ENCBTN:P = media_play_pause
"""


@dataclass(frozen=True)
class Config:
    settings: dict[str, str]
    triggers: dict[str, int | None]
    action_rules: list[dict[str, object]]
    notif_rules: list[dict[str, object]]
    display_blocks: dict[str, dict[str, object]]
    path: Path


class ConfigError(ValueError):
    """Raised when the config file cannot be parsed."""


def resolve_config_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    return CONFIG_FILE


def ensure_config(path: str | Path | None = None) -> Path:
    config_path = resolve_config_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return config_path


def load_config(path: str | Path | None = None) -> Config:
    config_path = ensure_config(path)
    text = config_path.read_text(encoding="utf-8")
    return parse_config(text, config_path)


def parse_config(text: str, path: str | Path = "<memory>") -> Config:
    settings: dict[str, str] = {}
    triggers: dict[str, int | None] = {}
    action_rules: list[dict[str, object]] = []
    notif_rules: list[dict[str, object]] = []
    display_blocks: dict[str, dict[str, object]] = {}

    lines = [_strip_comment(line) for line in text.splitlines()]
    top_sections = {"TRIGGERS", "ACTIONS", "NOTIFICATIONS"}

    current_section: str | None = None
    section_name: str | None = None
    section_body: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current_section, section_name, section_body
        if current_section is None:
            return
        if current_section == "TRIGGERS":
            triggers.update(_parse_triggers(section_body, path))
        elif current_section == "ACTIONS":
            action_rules.extend(_parse_actions_block(section_body))
        elif current_section == "NOTIFICATIONS":
            notif_rules.extend(_parse_notif_block(section_body))
        elif current_section == "DISPLAY":
            display_blocks[section_name or "DISPLAY"] = _parse_display_block(section_body)
        current_section = None
        section_name = None
        section_body = []

    for raw_line in lines:
        text_line = raw_line.strip()
        if not text_line:
            continue

        indent = _indent(raw_line)
        if indent == 0:
            keyword = text_line.split()[0].upper()
            if keyword in top_sections:
                flush()
                current_section = keyword
                section_name = keyword
                continue
            if keyword == "DISPLAY":
                flush()
                current_section = "DISPLAY"
                parts = text_line.split(None, 1)
                section_name = parts[1].strip() if len(parts) > 1 else "DISPLAY"
                continue
            if "=" in text_line:
                flush()
                key, _, value = text_line.partition("=")
                settings[key.strip()] = value.strip()
                continue

        if current_section is not None:
            section_body.append((indent, text_line))

    flush()
    return Config(settings, triggers, action_rules, notif_rules, display_blocks, Path(path))


def _strip_comment(line: str) -> str:
    in_quote = False
    quote_char = ""
    for index, char in enumerate(line):
        if char in {"'", '"'}:
            if not in_quote:
                in_quote = True
                quote_char = char
            elif quote_char == char:
                in_quote = False
                quote_char = ""
        if char == "#" and not in_quote:
            return line[:index].rstrip()
    return line


def _indent(line: str) -> int:
    count = 0
    for char in line:
        if char == "\t":
            count += 4
        elif char == " ":
            count += 1
        else:
            break
    return count


def _parse_triggers(lines: list[tuple[int, str]], path: str | Path) -> dict[str, int | None]:
    triggers: dict[str, int | None] = {}
    for _, text in lines:
        if "=" not in text:
            continue
        key, _, value = text.partition("=")
        value = value.strip()
        if value.lower() == "ontrigger":
            triggers[key.strip()] = None
            continue
        try:
            interval = int(value)
        except ValueError as exc:
            raise ConfigError(f"{path}: invalid trigger interval for {key.strip()!r}: {value!r}") from exc
        if interval <= 0:
            raise ConfigError(f"{path}: trigger interval must be positive for {key.strip()!r}")
        triggers[key.strip()] = interval
    return triggers


def _parse_actions_block(lines: list[tuple[int, str]]) -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        indent, text = lines[index]
        index += 1

        if "=" in text and not text.lower().startswith("if "):
            event, _, action = text.partition("=")
            event = event.strip()
            if event.split(":")[0] in {"BTN", "ENC", "ENCBTN"}:
                rules.append({"type": "binding", "event": event, "action": action.strip()})
            continue

        if text.lower().startswith("if ") and text.rstrip().endswith(":"):
            condition = _strip_then(text[3:].rstrip(":").strip())
            body: list[str] = []
            while index < len(lines) and lines[index][0] > indent:
                body.append(lines[index][1])
                index += 1
            rules.append({"type": "if", "condition": condition, "body": body})
    return rules


def _parse_notif_block(lines: list[tuple[int, str]]) -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        indent, text = lines[index]
        index += 1

        if not text.lower().startswith("if notif "):
            continue

        rest = _strip_then(text[9:].rstrip(":").strip())
        match_type: str | None = None
        value: str | None = None
        if rest.lower().startswith("from "):
            match_type = "from"
            value = rest[5:].strip().strip('"\'')
        elif rest.lower().startswith("contains "):
            match_type = "contains"
            value = rest[9:].strip().strip('"\'')

        if match_type and value:
            body: list[str] = []
            while index < len(lines) and lines[index][0] > indent:
                body.append(lines[index][1])
                index += 1
            rules.append({"match": match_type, "value": value, "body": body})
    return rules


def _parse_display_block(lines: list[tuple[int, str]]) -> dict[str, object]:
    if_blocks: list[dict[str, object]] = []
    tail: list[str] = []
    index = 0
    while index < len(lines):
        indent, text = lines[index]
        index += 1

        if text.lower().startswith("if ") and text.rstrip().endswith(":"):
            arg = _strip_then(text[3:].rstrip(":").strip())
            commands: list[str] = []
            while index < len(lines) and lines[index][0] > indent:
                commands.append(lines[index][1])
                index += 1
            if_blocks.append({"arg": arg, "commands": commands})
            continue

        tail.append(text)
    return {"if_blocks": if_blocks, "tail": tail}


def _strip_then(text: str) -> str:
    if text.lower().endswith(" then"):
        return text[:-5].strip()
    return text
