"""Desktop notification integration."""

from __future__ import annotations

import queue
import threading


def start_notification_watcher(notif_queue: queue.Queue[tuple[str, str]]) -> bool:
    try:
        import dbus
        import dbus.mainloop.glib
        from gi.repository import GLib
    except ImportError:
        print("[notif] dbus-python and PyGObject are required for notifications")
        return False

    def run() -> None:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()

        def on_notify(_sender, _dest, iface, member, _path, message) -> None:
            if iface != "org.freedesktop.Notifications" or member != "Notify":
                return
            try:
                app_name = str(message[0])
                summary = str(message[3]) if len(message) > 3 else ""
                body = str(message[4]) if len(message) > 4 else ""
            except (IndexError, TypeError):
                return
            notif_queue.put((app_name, f"{summary} {body}".strip()))

        bus.add_match_string("type='method_call',interface='org.freedesktop.Notifications'")
        bus.add_message_filter(on_notify)
        GLib.MainLoop().run()

    threading.Thread(target=run, daemon=True).start()
    return True


def notification_matches(rule: dict[str, object], app_name: str, text: str) -> bool:
    match_type = str(rule.get("match", ""))
    value = str(rule.get("value", ""))
    if match_type == "from":
        return app_name.lower() == value.lower()
    if match_type == "contains":
        return value.lower() in text.lower()
    return False
