# RaspDeck3

This repository contains everything related to the RaspDeck.  
RaspDeck is a small macro pad using the Waveshare RP2040-Zero.

## Features

- Customizable actions for every key
- Rotary encoder and encoder button support
- Customizable built-in LED colour and brightness
- 8x8 matrix display and SSD1306 support (WIP)
    
## Installation

1. Download the correct package for your distribution. (or download the source code)
2. Install the package.
3. Run `rd-tool --init-config` to create a configuration file.
4. Run `systemctl --user daemon-reload`.
5. Run `systemctl --user enable --now raspdeck-daemon.service` to enable the daemon.
6. (Optional) Run `systemctl --user enable --now raspdeck-tray.service` to enable the tray.
    
## License
This project is released under the GNU GPL v3 license.
