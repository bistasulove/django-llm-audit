# django-llm-audit

[![CI](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/bistasulove/django-llm-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)

> Run `python manage.py audit_model --model Order` and get a plain-English business
> intelligence report on your data in seconds.

`django-llm-audit` is a reusable Django plugin that points a Large Language Model at any
Django model and returns intelligent summaries, trend analysis, and anomaly reports —
entirely from the terminal via a management command.

> **Status:** 🚧 Early development. This README is a placeholder; the full documentation
> lands in milestone M7. See [`CLAUDE.md`](CLAUDE.md) for the project plan and roadmap.

## Why

- Zero migrations, zero models, zero coupling to your code — it only *reads* your data.
- Provider-agnostic: pluggable backends for Anthropic, OpenAI, and more.
- Token-aware: chunks large datasets so they fit the model's context window.

## Quickstart (target experience)

```python
# settings.py
INSTALLED_APPS = ["llm_audit"]

LLM_AUDIT = {
    "BACKEND": "llm_audit.backends.anthropic.AnthropicBackend",
    "API_KEY": env("ANTHROPIC_API_KEY"),
}
```

```bash
python manage.py audit_model --app store --model Order --limit 100
```

## Development

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
python demo/manage.py migrate
python demo/manage.py seed_data
pytest
```

## License

[MIT](LICENSE) © 2026 Sulav Raj Bista
