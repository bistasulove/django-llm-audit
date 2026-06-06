# django-llm-audit

[![CI](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)

> Run `python manage.py audit_model --model Order` and get a plain-English business
> intelligence report on your data in seconds.

`django-llm-audit` is a reusable Django plugin that points a Large Language Model at any
Django model and returns intelligent summaries, trend analysis, and anomaly reports —
entirely from the terminal via a management command.

> **Status:** 🚧 Early development — milestone **M5 (pluggable backends)** is functional.
> The `audit_model` command produces a real summary today, handles large datasets by
> chunking them and summarizing map-reduce style, can stream the report token-by-token with
> `--stream`, can emit a validated structured report as JSON or Markdown with `--format`, and
> runs against any configured LLM backend (Anthropic or OpenAI built in, swappable via
> settings or `--backend`). The full documentation lands in milestone M7. See
> [`CLAUDE.md`](CLAUDE.md) for the roadmap and [`CHANGELOG.md`](CHANGELOG.md) for what has
> shipped.

## Why

- Zero migrations, zero models, zero coupling to your code — it only *reads* your data.
- Provider-agnostic by design: pluggable LLM backends (Anthropic and OpenAI built in; write your own).
- Token-aware: chunks large datasets so they fit the model's context window, then summarizes map-reduce style.
- Structured output: get a validated JSON or Markdown report (Pydantic-checked), not just free text.

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

# stream the report token-by-token as it is generated
python manage.py audit_model --app store --model Order --limit 50 --stream

# get a validated structured report as JSON or Markdown (optionally written to a file)
python manage.py audit_model --app store --model Order --format json
python manage.py audit_model --app store --model Order --format markdown --output report.md
```

## What works today (M5)

The command resolves a model, serializes up to `--limit` records to JSON, splits them into
token-safe chunks, and summarizes them. Datasets that exceed `CHUNK_TOKEN_THRESHOLD` are
summarized **map-reduce style**: each chunk is summarized on its own, then those partial
summaries are combined into one final report. Small datasets that fit in a single chunk
skip the reduce step and cost just one call.

Output comes in two shapes:

- **Prose** (`--format text`, the default) — a plain-text summary (headline, patterns,
  anomalies, assessment). With `--stream` it prints token-by-token as it is generated,
  followed by an estimated token tally. In a multi-chunk run only the final combined report
  streams — the per-chunk summaries must complete first, since they feed the combine step.
- **Structured** (`--format json` or `--format markdown`) — the LLM is asked to return JSON,
  which is validated with Pydantic into a `SummaryReport` (retried up to twice if the model
  returns malformed or off-schema output) and then rendered. Metadata like the model name,
  record count, and timestamp is filled in by the plugin, not the LLM. Structured output is
  buffered to validate, so `--stream` does not apply to it. `--output <path>` writes the
  rendered report to a file.

| Flag | Status in M4 |
|------|--------------|
| `--app`, `--model` | ✅ honored (defaults to `store.Order`) |
| `--limit` | ✅ honored (default 50) — a safety cap; chunking handles the token budget |
| `--stream` | ✅ honored for `--format text`; ignored (with a warning) for structured formats |
| `--format` | ✅ honored — `text` (default), `json`, `markdown` |
| `--output` | ✅ honored — writes the rendered report to a file |
| `--backend` | ✅ honored — dotted path overriding `LLM_AUDIT["BACKEND"]` for one run |
| `--fields`, `--filter` | ⏳ parsed but not yet wired (later milestones) |

## Configuration

All settings live under `LLM_AUDIT` in your Django settings, read through the plugin's
settings accessor with these defaults:

| Key | Default | Meaning |
|-----|---------|---------|
| `BACKEND` | `llm_audit.backends.anthropic.AnthropicBackend` | Dotted path to the LLM backend class. |
| `API_KEY` | `None` | Your provider API key. Required by the real backends; `MockBackend` ignores it. |
| `MODEL` | `claude-haiku-4-5-20251001` | LLM model id. |
| `MAX_TOKENS` | `1024` | Max tokens in the LLM response. |
| `CHUNK_TOKEN_THRESHOLD` | `3000` | Max estimated tokens of records JSON per chunk. |
| `DEFAULT_RECORD_LIMIT` | `50` | Default `--limit` when not specified. |

## Backends

Every LLM call goes through a backend implementing `BaseLLMBackend`. The plugin depends on
that abstraction, never on a provider SDK, so switching providers is a settings change — not
a code change. You pick one with `LLM_AUDIT["BACKEND"]` (a dotted path), and override it for
a single run with `--backend`.

| Backend | Dotted path | Install |
|---------|-------------|---------|
| Anthropic (Claude) | `llm_audit.backends.anthropic.AnthropicBackend` | `pip install django-llm-audit[anthropic]` |
| OpenAI (GPT) | `llm_audit.backends.openai.OpenAIBackend` | `pip install django-llm-audit[openai]` |
| Mock (tests/offline) | `llm_audit.backends.mock.MockBackend` | _(built in; no SDK, no API key)_ |

```bash
# one-off run against OpenAI without changing settings
python manage.py audit_model --backend llm_audit.backends.openai.OpenAIBackend
```

`MockBackend` returns deterministic output with no network call and no API key — point your
test settings at it to exercise the whole pipeline offline:

```python
LLM_AUDIT = {"BACKEND": "llm_audit.backends.mock.MockBackend"}
```

### Writing a custom backend

Subclass `BaseLLMBackend` and implement `complete` and `stream` (`count_tokens` has a sane
default). Construct it with `api_key` / `model` / `max_tokens` keyword arguments — the same
shape the factory uses for every backend:

```python
from collections.abc import Generator
from llm_audit.backends.base import BaseLLMBackend

class MyBackend(BaseLLMBackend):
    def __init__(self, api_key, model, max_tokens):
        ...

    def complete(self, prompt: str, system: str | None = None) -> str:
        ...

    def stream(self, prompt: str, system: str | None = None) -> Generator[str, None, None]:
        yield ...
```

Then point settings at it: `LLM_AUDIT["BACKEND"] = "myapp.backends.MyBackend"`.

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
