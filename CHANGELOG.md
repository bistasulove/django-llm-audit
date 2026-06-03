# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **M0 — Repo scaffolding & demo app**
  - Project packaging via `pyproject.toml` (hatchling build backend, dynamic version).
  - `llm_audit/` plugin package skeleton with stub modules and management command.
  - Settings accessor (`llm_audit/conf.py`) with defaults.
  - `demo/` Django project with a `store` e-commerce app (Category, Product, Order, OrderItem).
  - `seed_data` management command (faker-based, idempotent, `--reset` flag, baked-in anomalies).
  - `pytest` + `pytest-django` test scaffolding.
  - `pre-commit` with `ruff` and `black`.
  - GitHub Actions CI workflow.
