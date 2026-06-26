# Serial Protocol

Serial is newline-delimited text at 115200 baud.

## Firmware to Host

```text
BTN:<id>:P
BTN:<id>:R
ENC:+1
ENC:-1
ENCBTN:P
ENCBTN:R
pong
```

## Host to Firmware

```text
ping
clear
bright <0-15>
pixel <0-63> <0|1>
pixels <64-char 01 bitmap>
pixels -h <comma-separated indexes>
led -c <RRGGBB>
led -b <0-100>
```
