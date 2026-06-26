# Daemon

The daemon keeps the serial connection open and turns RaspDeck events into
actions.

## What It Does

- finds the device
- reads `~/.config/raspdeck/config.conf`
- listens for button and encoder events
- runs actions from the config
- watches desktop notifications when configured

## Config

The config file is:

```text
~/.config/raspdeck/config.conf
```
