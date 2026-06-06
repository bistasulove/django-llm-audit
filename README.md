# django-llm-audit

[![CI](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/bistasulove/django-llm-audit/branch/master/graph/badge.svg)](https://codecov.io/gh/bistasulove/django-llm-audit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)

> Run `python manage.py audit_model --model Order` and get a plain-English business
> intelligence report on your data in seconds.

`django-llm-audit` is a reusable Django plugin that points a Large Language Model at any
Django model and returns intelligent summaries, trend analysis, and anomaly reports —
entirely from the terminal via a management command.

> **Status:** 🚧 Early development — milestone **M6 (tests & CI)** is complete.
> The `audit_model` command produces a real summary today, handles large datasets by
> chunking them and summarizing map-reduce style, can stream the report token-by-token with
> `--stream`, can emit a validated structured report as JSON or Markdown with `--format`, and
> runs against any configured LLM backend (Anthropic, OpenAI, and a local Ollama backend
> built in, swappable via settings or `--backend`). It ships with a full test suite (the LLM
> is mocked, the data is real) gated at >80% coverage in CI across Python 3.10–3.12. The full
> documentation lands in milestone M7. See
> [`CLAUDE.md`](CLAUDE.md) for the roadmap and [`CHANGELOG.md`](CHANGELOG.md) for what has
> shipped.

## Why

- Zero migrations, zero models, zero coupling to your code — it only *reads* your data.
- Provider-agnostic by design: pluggable LLM backends (Anthropic, OpenAI, and local Ollama built in; write your own).
- Run it fully local and key-free with [Ollama](https://ollama.com) — your data never leaves the machine.
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

# Cloud provider (Anthropic shown; "openai" works the same way):
LLM_AUDIT = {
    "BACKEND": "anthropic",                 # short alias; the full dotted path also works
    "API_KEY": os.environ["ANTHROPIC_API_KEY"],
    "MODEL": "claude-haiku-4-5-20251001",   # default; override with any Claude model id
}

# ...or run a local model with Ollama — no API key, nothing leaves your machine:
LLM_AUDIT = {
    "BACKEND": "ollama",
    "MODEL": "llama3.1",                     # any model you've `ollama pull`ed
    # host defaults to http://localhost:11434; override with the OLLAMA_HOST env var
}
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# the report streams token-by-token to your terminal by default
python manage.py audit_model --app store --model Order --limit 50

# opt out of streaming (e.g. for scripting or piping)
python manage.py audit_model --app store --model Order --limit 50 --no-stream

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
  anomalies, assessment). It **streams token-by-token to your terminal by default**, followed
  by an estimated token tally; pass `--no-stream` to buffer instead. In a multi-chunk run only
  the final combined report streams — the per-chunk summaries must complete first, since they
  feed the combine step. While the model works, a short status line fills the wait.
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
| `--stream` / `--no-stream` | ✅ streaming is **on by default** for `--format text` to the terminal; `--no-stream` opts out. Automatically off (buffered) for structured formats and file output |
| `--format` | ✅ honored — `text` (default), `json`, `markdown` |
| `--output` | ✅ honored — writes the rendered report to a file |
| `--backend` | ✅ honored — selects a named backend (class + key + model) for one run, or overrides the class in a flat config |
| `--fields`, `--filter` | ⏳ parsed but not yet wired (later milestones) |

## Configuration

All settings live under `LLM_AUDIT` in your Django settings. There are two shapes — use the
flat one for a single provider, or named backends when you want to switch between several.

**Flat (single provider):**

| Key | Default | Meaning |
|-----|---------|---------|
| `BACKEND` | `anthropic` | Which backend to use: a short alias (`anthropic`, `openai`, `ollama`, `mock`) or a full dotted path. |
| `API_KEY` | `None` | Your provider API key. Required by the real backends; `MockBackend` and `OllamaBackend` ignore it. |
| `MODEL` | `claude-haiku-4-5-20251001` | LLM model id. |
| `MAX_TOKENS` | `1024` | Max tokens in the LLM response. |
| `CHUNK_TOKEN_THRESHOLD` | `3000` | Max estimated tokens of records JSON per chunk. |
| `DEFAULT_RECORD_LIMIT` | `50` | Default `--limit` when not specified. |

**Named backends (switch providers per run):** add a `BACKENDS` dict of self-contained
bundles and a `DEFAULT` naming the one to use when `--backend` is omitted — the same idea as
Django's `DATABASES` + `--database`. Each bundle needs its own `BACKEND` (plus `API_KEY` /
`MODEL` as the provider requires); `MAX_TOKENS` may be set per bundle or shared at the top
level. The pipeline-wide keys (`CHUNK_TOKEN_THRESHOLD`, `DEFAULT_RECORD_LIMIT`) always live at
the top level.

```python
LLM_AUDIT = {
    "DEFAULT": "anthropic",
    "BACKENDS": {
        "anthropic": {"BACKEND": "anthropic", "API_KEY": os.environ["ANTHROPIC_API_KEY"], "MODEL": "claude-haiku-4-5-20251001"},
        "openai":    {"BACKEND": "openai",    "API_KEY": os.environ["OPENAI_API_KEY"],    "MODEL": "gpt-4o"},
        "ollama":    {"BACKEND": "ollama",    "MODEL": "llama3.1"},   # local, no key
    },
    "MAX_TOKENS": 1024,
    "CHUNK_TOKEN_THRESHOLD": 3000,
    "DEFAULT_RECORD_LIMIT": 50,
}
```

```bash
python manage.py audit_model --model Order              # uses DEFAULT ("anthropic")
python manage.py audit_model --model Order --backend openai   # switches class + key + model
```

## Backends

Every LLM call goes through a backend implementing `BaseLLMBackend`. The plugin depends on
that abstraction, never on a provider SDK, so switching providers is a settings change — not
a code change. You pick one with `LLM_AUDIT` (flat `BACKEND`, or named `BACKENDS` + `DEFAULT`
as shown in [Configuration](#configuration)) and override it for a single run with `--backend`.
A `BACKEND` value can be a short **alias** or a full dotted path:

| Backend | Alias | Dotted path | Install |
|---------|-------|-------------|---------|
| Anthropic (Claude) | `anthropic` | `llm_audit.backends.anthropic.AnthropicBackend` | `pip install django-llm-audit[anthropic]` |
| OpenAI (GPT) | `openai` | `llm_audit.backends.openai.OpenAIBackend` | `pip install django-llm-audit[openai]` |
| Ollama (local) | `ollama` | `llm_audit.backends.ollama.OllamaBackend` | _(built in; no SDK — just a running Ollama)_ |
| Mock (tests/offline) | `mock` | `llm_audit.backends.mock.MockBackend` | _(built in; no SDK, no API key)_ |

```bash
# one-off run against OpenAI without changing settings
python manage.py audit_model --backend openai
```

### Local models with Ollama

The Ollama backend talks to a [local Ollama](https://ollama.com) server over plain HTTP, so it
needs **no API key and no extra Python package** — only a running Ollama with your model pulled:

```bash
ollama serve            # start the server (often already running)
ollama pull llama3.1    # pull a model once

python manage.py audit_model --backend ollama --model Order
```

Point `LLM_AUDIT["MODEL"]` at any tag you've pulled. The host defaults to
`http://localhost:11434`; set the `OLLAMA_HOST` environment variable to reach a server on
another address. If Ollama isn't running you get a clear, actionable error rather than a
traceback.

`MockBackend` returns deterministic output with no network call and no API key — point your
test settings at it to exercise the whole pipeline offline:

```python
LLM_AUDIT = {"BACKEND": "llm_audit.backends.mock.MockBackend"}
```

### Writing a custom backend

Subclass `BaseLLMBackend` and implement `complete` and `stream` (`count_tokens` has a sane
default). Construct it with `api_key` / `model` / `max_tokens` keyword arguments — the same
shape the factory uses for every backend. Store `self.model` so the run banner can report it:

```python
from collections.abc import Generator
from llm_audit.backends.base import BaseLLMBackend

class MyBackend(BaseLLMBackend):
    def __init__(self, api_key, model, max_tokens):
        self.model = model
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
pytest --cov=llm_audit --cov-report=term-missing   # with coverage (gated at >80% in CI)
ruff check . && black --check .
```

Tests follow CLAUDE.md §11: the LLM (an external I/O dependency) is mocked via the shipped
`MockBackend`, while the data is real — a tiny test-only `testapp.Order` model is seeded and
audited end-to-end through `call_command`. No test ever spends a token or needs a key.

The `demo/` project loads `.env` from the repo root via `python-dotenv`, so the demo picks
up `ANTHROPIC_API_KEY` automatically.

## License

[MIT](LICENSE) © 2026 Sulav Raj Bista
