# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- **M3** — `summarizer.summarize()` gained a `stream` flag and now funnels every run
  through a single terminal backend call (the stream-vs-complete decision point); the old
  `_summarize_chunk` helper became `_build_chunk_prompt` (prompt construction only, no
  backend call).
- **M2** — `audit_model` now hands off to `summarizer.summarize` instead of serializing and
  calling the backend inline; large record sets are handled transparently. `--limit` is now
  a safety cap rather than the token constraint.
- **M1** — Default `LLM_AUDIT["MODEL"]` updated from the stale `claude-opus-4-5` to
  `claude-haiku-4-5-20251001` (cheap/fast default; demo uses the same).
