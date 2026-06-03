# django-llm-audit

[![CI](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)

> Run `python manage.py audit_model --model Order` and get a plain-English business
> intelligence report on your data in seconds.

`django-llm-audit` is a reusable Django plugin that points a Large Language Model at any
Django model and returns intelligent summaries, trend analysis, and anomaly reports —
entirely from the terminal via a management command.

> **Status:** 🚧 Early development — milestone **M1 (bare LLM call)** is functional. The
> `audit_model` command produces a real summary today via the Anthropic backend. The full
> documentation lands in milestone M7. See [`CLAUDE.md`](CLAUDE.md) for the roadmap and
> [`CHANGELOG.md`](CHANGELOG.md) for what has shipped.

## Why

- Zero migrations, zero models, zero coupling to your code — it only *reads* your data.
- Provider-agnostic by design: pluggable LLM backends _(Anthropic today; OpenAI and others land in M5)_.
- Token-aware: chunks large datasets so they fit the model's context window _(arrives in M2)_.

## Install

```bash
pip install django-llm-audit[anthropic]   # the anthropic extra pulls in the Claude SDK
```

> Not yet on PyPI — that's the M8 deliverable. For now, install from source (see
> [Development](#development) below).

## Quickstart

```python
# settings.py
INSTALLED_APPS = ["llm_audit"]

LLM_AUDIT = {
    "BACKEND": "llm_audit.backends.anthropic.AnthropicBackend",
    "API_KEY": os.environ["ANTHROPIC_API_KEY"],
    "MODEL": "claude-haiku-4-5-20251001",   # default; override with any Claude model id
}
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python manage.py audit_model --app store --model Order --limit 50
```

## What works today (M1)

The command resolves a model, serializes up to `--limit` records to JSON, and asks the
LLM for a structured plain-text summary (headline, patterns, anomalies, assessment).

| Flag | Status in M1 |
|------|--------------|
| `--app`, `--model` | ✅ honored (defaults to `store.Order`) |
| `--limit` | ✅ honored (default 50) |
| `--fields`, `--filter`, `--output`, `--format`, `--stream`, `--backend` | ⏳ parsed but not yet wired (later milestones) |

Not yet implemented: token-aware chunking (M2), streaming (M3), structured/JSON output
(M4), and non-Anthropic backends (M5). Large record sets are sent in a single request for
now, so keep `--limit` modest.

## Configuration

All settings live under `LLM_AUDIT` in your Django settings, read through the plugin's
settings accessor with these defaults:

| Key | Default | Meaning |
|-----|---------|---------|
| `BACKEND` | _(required)_ | Dotted path to the LLM backend class. |
| `API_KEY` | _(required)_ | Your provider API key. |
| `MODEL` | `claude-haiku-4-5-20251001` | LLM model id. |
| `MAX_TOKENS` | `1024` | Max tokens in the LLM response. |
| `CHUNK_TOKEN_THRESHOLD` | `3000` | Max tokens per chunk _(used from M2)_. |
| `DEFAULT_RECORD_LIMIT` | `50` | Default `--limit` when not specified. |

## Development

```bash
uv venv --python 3.12
uv pip install -e ".[dev,anthropic]"

# run the bundled demo store
cp .env.example .env                  # then put your real ANTHROPIC_API_KEY in it
python demo/manage.py migrate
python demo/manage.py seed_data       # idempotent; --reset to wipe & reseed
python demo/manage.py audit_model --limit 50

pytest                                # tests run without an API key (none reach the LLM)
ruff check . && black --check .
```

The `demo/` project loads `.env` from the repo root via `python-dotenv`, so the demo picks
up `ANTHROPIC_API_KEY` automatically.

## License

[MIT](LICENSE) © 2026 Sulav Raj Bista
