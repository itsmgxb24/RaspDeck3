from raspdeck.core.config import parse_config


def test_parse_config_sections():
    config = parse_config(
        """
BRIGHT = 9

TRIGGERS
    DISPLAY = onTrigger
    VOLUME = 250

ACTIONS
    BTN:0:P = log=hello
    if volume() then:
        trigger DISPLAY(vol)

NOTIFICATIONS
    if notif contains "Discord" then:
        trigger DISPLAY(discord)

DISPLAY
    if vol then:
        VOLUME.vertical_top(2)
    wait 500
    clear
"""
    )

    assert config.settings["BRIGHT"] == "9"
    assert config.triggers == {"DISPLAY": None, "VOLUME": 250}
    assert config.action_rules[0]["event"] == "BTN:0:P"
    assert config.notif_rules[0]["match"] == "contains"
    assert "DISPLAY" in config.display_blocks


def test_comment_inside_quotes_is_kept():
    config = parse_config(
        """
NOTIFICATIONS
    if notif contains "build #42" then:
        log=ok
"""
    )

    assert config.notif_rules[0]["value"] == "build #42"
