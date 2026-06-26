from raspdeck.core.display import parse_pixels_arg, parse_volume_cmd, volume_pixels


def test_parse_human_readable_pixels():
    pixels = parse_pixels_arg("-h 0, 2, 63, nope")

    assert pixels is not None
    assert pixels[0] == 1
    assert pixels[2] == 1
    assert pixels[63] == 1
    assert sum(pixels) == 3


def test_parse_volume_limit():
    assert parse_volume_cmd("VOLUME.vertical_top(2)") == ("vertical_top", 2)
    assert parse_volume_cmd("VOLUME.horizontal_left") == ("horizontal_left", 8)


def test_volume_pixels_clamps_percent():
    pixels = volume_pixels("vertical_top", 1, 150)

    assert sum(pixels) == 8
