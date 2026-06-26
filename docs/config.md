# Config Format

RaspDeck config is plain text.

Top-level settings use `KEY = VALUE`.

Comments start with `#`.

```conf
BRIGHT = 8
# PORT = /dev/ttyACM0
```

Sections are indentation-based:

- `TRIGGERS`
- `ACTIONS`
- `NOTIFICATIONS`

Display config is not documented yet.

See `config/examples/default.conf`.
