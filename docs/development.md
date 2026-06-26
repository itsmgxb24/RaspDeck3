# Development

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,daemon,tray,notifications]'
```

## Checks

```sh
ruff check src tests
pytest
```
