# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

- Default `LLM_AUDIT["MODEL"]` updated from the stale `claude-opus-4-5` to
  `claude-haiku-4-5-20251001` (cheap/fast default; demo uses the same).

- **M0 — Repo scaffolding & demo app**
  - Project packaging via `pyproject.toml` (hatchling build backend, dynamic version).
  - `llm_audit/` plugin package skeleton with stub modules and management command.
  - Settings accessor (`llm_audit/conf.py`) with defaults.
  - `demo/` Django project with a `store` e-commerce app (Category, Product, Order, OrderItem).
  - `seed_data` management command (faker-based, idempotent, `--reset` flag, baked-in anomalies).
  - `pytest` + `pytest-django` test scaffolding.
  - `pre-commit` with `ruff` and `black`.
  - GitHub Actions CI workflow.
