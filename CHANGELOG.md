# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **M5 — Pluggable LLM backends**
  - `BaseLLMBackend` (`backends/base.py`) is now the formal interface every backend
    implements — `complete(prompt, system=...)` and `stream(prompt, system=...)`, plus a
    concrete `count_tokens` default (the `len // 4` heuristic; override for exact counts).
    The summarizer and command depend on this abstraction, never on a provider SDK
    (Dependency Inversion).
  - `get_backend()` (`backends/__init__.py`) — a factory that resolves the configured
    dotted path to a backend class via Django's `import_string` and instantiates it with
    standard `api_key`/`model`/`max_tokens` kwargs. Selection precedence: `--backend`
    override → `LLM_AUDIT["BACKEND"]` → default. A bad path raises `ImproperlyConfigured`.
  - `--backend <dotted.path>` is now honored — override the configured backend for one run.
  - `OpenAIBackend` (`backends/openai.py`) — full `complete()` + `stream()` over the OpenAI
    Chat Completions API. Carries the system prompt *inside* the `messages` array (vs.
    Anthropic's top-level `system`), proving the abstraction holds across two real providers.
    Lazy `openai` import; errors wrapped as `LLMBackendError`.
  - `MockBackend` (`backends/mock.py`) — a deterministic, offline backend that needs no API
    key. Returns prose for the free-text path and a schema-valid `ReportBody` JSON for the
    structured path (detected via the system prompt). Ships in the package so downstream
    users can point their test settings at it; `mock_backend` pytest fixture added.
  - `conf.py` DEFAULTS gained `BACKEND` (default Anthropic) and `API_KEY` (default `None`),
    so the plugin imports and `MockBackend` runs with zero configuration.
  - Backend tests (`test_backends.py`): interface conformance, the factory's
    resolution/override/bad-path behaviour, `MockBackend`'s output shapes, and missing-key
    rejection by the real backends.
  - **Streaming by default** for interactive prose: `--format text` to the terminal now
    streams token-by-token without any flag. `--stream`/`--no-stream` (argparse
    `BooleanOptionalAction`) toggle it; `--no-stream` opts out for scripting/piping.
    Streaming is automatically disabled where it cannot apply — structured formats (must
    buffer to validate) and file output (no cursor to animate) — and the "ignored" warning
    now fires only when `--stream` was passed explicitly. A whimsical status line fills the
    wait while the model works, so the previously silent single-chunk case now speaks. The
    stream decision lives in a pure, unit-tested `_resolve_stream` helper.

- **M4 — Structured output with Pydantic**
  - `--format json` and `--format markdown` switch `audit_model` to a *structured* path:
    the LLM is asked to return JSON, which is validated into a `SummaryReport` and then
    rendered. `--format text` (the default) keeps the free-text prose path.
  - `--output <path>` writes the rendered report to a file instead of stdout.
  - `schemas/report.py` — `Anomaly`, `ReportBody` (the analytical fields the LLM returns),
    and `SummaryReport` (`ReportBody` plus metadata — `model_name`, `record_count`,
    `generated_at` — injected in Python, never asked of the LLM). `severity` is a strict
    `Literal["low", "medium", "high"]`.
  - `formatters.py` — pure `text` / `json` / `markdown` renderers over a `SummaryReport`.
  - `prompts.py` — structured `build_structured_audit_prompt()` /
    `build_structured_meta_prompt()` whose JSON example is built from a real validated
    `ReportBody`, so the prompt can never drift from the schema.
  - `summarizer.summarize(structured=True)` returns a validated `SummaryReport`. The
    terminal call is parsed, validated, and **retried** (up to 2 times) with the specific
    error fed back to the model; exhausting retries raises the new `StructuredOutputError`.
    In a multi-chunk run only the reduce call is structured — the map calls stay prose.
  - Unit tests for the schemas, the formatters, and the structured summarizer path
    (including retry-then-succeed, schema-violation retry, and retry exhaustion).

- **M3 — Streaming output**
  - `audit_model --stream` prints the final report token-by-token as it arrives instead
    of all at once. After the stream ends it prints an estimated token tally
    (`~N tokens received`) to build intuition for response size.
  - `AnthropicBackend.stream()` — a generator over Anthropic's streaming Messages API
    (`client.messages.stream(...).text_stream`), mirroring `complete()`'s error handling.
  - In a multi-chunk run, only the final reduce call streams; the per-chunk map calls
    stay blocking, because the reduce step needs each chunk summary's full text first.

- **M2 — Token-aware chunking**
  - `chunker.py` — `chunk_records()` packs records greedily into chunks that each stay
    under `CHUNK_TOKEN_THRESHOLD`, plus `estimate_tokens()` (the `len(text) // 4`
    approximation). A single record larger than the threshold is emitted as its own chunk
    rather than failing the run; a non-positive threshold raises `ChunkingError`.
  - `serializer.py` — `serialize_records()` extracted from M1's inline `json.dumps`; pure,
    Django-free, `default=str`, with a compact (`indent=None`) option for prompts.
  - `summarizer.py` — `summarize()` orchestrates map-reduce: one call when the data fits a
    single chunk, otherwise summarize each chunk (map) and combine the partials (reduce).
    Takes an injected backend and an optional `notify` callback for progress/warnings.
  - `prompts.py` — `build_meta_prompt()` + `META_SYSTEM_PROMPT` for the reduce step, shaped
    to match the single-chunk output.
  - Real unit tests for `chunker`, `serializer`, and `summarizer` (the last via a local
    fake backend), replacing the M0 placeholders.

- **M1 — Bare LLM call (no abstraction)**
  - `audit_model` command now produces a real LLM summary: resolves a model via
    `--app`/`--model` (defaulting to `store.Order`), serializes records inline with
    `json.dumps(default=str)`, and prints Claude's response.
  - `AnthropicBackend.complete()` — a plain wrapper over the Anthropic Messages API
    (no `BaseLLMBackend` inheritance yet; that lands in M5). Lazy SDK import with a
    helpful install hint.
  - `build_audit_prompt()` in `prompts.py` — system/user prompt split, with grounding
    that lists the available fields, states the extract is flat/single-table, and tells
    the model to separate genuine anomalies from data artifacts and flag missing-data
    conclusions instead of inventing them.
  - `python-dotenv` loads a repo-root `.env` in the demo settings.
  - Graceful handling of unknown models, empty querysets, and backend errors (all
    surface as clean `CommandError`s).

- **M0 — Repo scaffolding & demo app**
  - Project packaging via `pyproject.toml` (hatchling build backend, dynamic version).
  - `llm_audit/` plugin package skeleton with stub modules and management command.
  - Settings accessor (`llm_audit/conf.py`) with defaults.
  - `demo/` Django project with a `store` e-commerce app (Category, Product, Order, OrderItem).
  - `seed_data` management command (faker-based, idempotent, `--reset` flag, baked-in anomalies).
  - `pytest` + `pytest-django` test scaffolding.
  - `pre-commit` with `ruff` and `black`.
  - GitHub Actions CI workflow.

### Changed

- **M5** — `audit_model` no longer names a concrete backend: it calls `get_backend()` instead
  of constructing `AnthropicBackend` directly. `AnthropicBackend` now inherits
  `BaseLLMBackend` (its method bodies were unchanged — the interface was reverse-engineered
  from code that had worked since M1). The `BaseLLMBackend` ABC signatures were finalized to
  include the `system` argument the summarizer already passes.
- **M5** — Streaming is now the **default** for interactive `--format text` output (previously
  opt-in via `--stream`). `--stream` became a `--stream`/`--no-stream` pair; non-streaming is
  still automatic for structured formats and file output.
- **M4** — `summarizer.summarize()` gained `structured` and `max_retries` parameters and can
  now return a `SummaryReport` (in addition to a string or a streaming generator). `audit_model`
  routes on `--format`: structured formats buffer and validate, so `--stream` is ignored (with a
  warning) when combined with `--format json`/`markdown`.
- **M3** — `summarizer.summarize()` gained a `stream` flag and now funnels every run
  through a single terminal backend call (the stream-vs-complete decision point); the old
  `_summarize_chunk` helper became `_build_chunk_prompt` (prompt construction only, no
  backend call).
- **M2** — `audit_model` now hands off to `summarizer.summarize` instead of serializing and
  calling the backend inline; large record sets are handled transparently. `--limit` is now
  a safety cap rather than the token constraint.
- **M1** — Default `LLM_AUDIT["MODEL"]` updated from the stale `claude-opus-4-5` to
  `claude-haiku-4-5-20251001` (cheap/fast default; demo uses the same).
