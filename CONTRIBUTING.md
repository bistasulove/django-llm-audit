# Contributing to django-llm-audit

Thanks for your interest in contributing! This project is built in public as a learning
vehicle — see [`CLAUDE.md`](CLAUDE.md) for the full architecture and roadmap.

## Development setup

```bash
git clone https://github.com/bistasulove/django-llm-audit
cd django-llm-audit

uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

pre-commit install
```

## Running things

```bash
python demo/manage.py migrate     # set up the demo database
python demo/manage.py seed_data   # generate realistic fake data
pytest                            # run the test suite
pre-commit run --all-files        # lint + format
```

## Conventions

- **Formatter:** `black` (line length 100).
- **Linter:** `ruff`.
- **Type hints** on all public functions; **Google-style docstrings** on public APIs.
- **Commit messages:** `<type>: <short description>` where type is one of
  `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `style`.

## The golden rule

`llm_audit/` must never import from `demo/`. The demo depends on the plugin, never the
reverse. This one-way dependency keeps the plugin independent and installable on its own.
