# CLAUDE.md — django-llm-audit
> Source of truth for the project. Read this before touching any code.
> Last updated: 2026-06-03

---

## Table of Contents

1. [Project Identity](#1-project-identity)
2. [Learning Philosophy](#2-learning-philosophy)
3. [Architecture Decisions](#3-architecture-decisions)
4. [Repository Structure](#4-repository-structure)
5. [The Demo App](#5-the-demo-app)
6. [The Plugin (`llm_audit`)](#6-the-plugin-llm_audit)
7. [LLM Design Principles](#7-llm-design-principles)
8. [Configuration System](#8-configuration-system)
9. [Complete Milestone Roadmap](#9-complete-milestone-roadmap)
10. [Packaging & Release Strategy](#10-packaging--release-strategy)
11. [Testing Strategy](#11-testing-strategy)
12. [Documentation Strategy](#12-documentation-strategy)
13. [Building in Public](#13-building-in-public)
14. [Conventions & Code Style](#14-conventions--code-style)
15. [Decisions Log](#15-decisions-log)

---

## 1. Project Identity

### What is this?

`django-llm-audit` is a reusable Django plugin that lets developers point a Large Language Model
at any Django model and receive intelligent summaries, trend analysis, and anomaly reports —
entirely from the terminal via Django management commands.

### One-line pitch

> "Run `python manage.py audit_model --model Order` and get a plain-English business intelligence
> report on your data in seconds."

### Target users

- Django developers who want quick LLM-powered insight into their production/staging data
- Small teams without a dedicated data analyst
- Developers learning to integrate LLMs into real backend systems

### What it is NOT

- It is not a full BI dashboard (no UI, no charts, no frontend)
- It is not an ORM query builder (it doesn't write SQL for you)
- It is not a data pipeline (it doesn't transform or migrate data)
- It is not tightly coupled to any single LLM provider

### Target installation experience

```python
# 1. Install
# pip install django-llm-audit

# 2. Add to settings.py
INSTALLED_APPS = ["llm_audit"]

LLM_AUDIT = {
    "BACKEND": "llm_audit.backends.anthropic.AnthropicBackend",
    "API_KEY": env("ANTHROPIC_API_KEY"),
}

# 3. Run
# python manage.py audit_model --app store --model Order --limit 100
```

That's the full integration. Zero migrations, zero model changes, zero coupling to user's code.

---

## 2. Learning Philosophy

This project is explicitly a learning vehicle. Every decision in this codebase has been made to
maximize depth of understanding, not speed of delivery.

### Principles

**Build before abstracting.** Each milestone starts with the simplest direct implementation.
Abstractions are introduced only after you've felt the pain they solve. Never add a layer of
indirection unless you have personally hit the wall that layer fixes.

**Understand the why.** Every architectural decision in this file includes a "Why?" and a
"Tradeoffs" section. When you write code, you should be able to explain every line. If you can't,
that's a signal to slow down and understand before proceeding.

**Concepts before code.** Each milestone begins with a concepts section — what you're learning,
why it matters in the AI engineering world, and how it connects to the broader RAG/agent landscape.

**Mistakes are curriculum.** Intentionally do things the naive way first (e.g., no chunking, no
streaming) so you can feel why the improved version matters. This is more valuable than being
handed the "right" answer.

**Production thinking from day one.** Even in early milestones, ask: "How would this behave in
production?" Think about token costs, latency, error rates, and API limits — not just correctness.

---

## 3. Architecture Decisions

### ADR-001: Python package, not a Django app with migrations

**Decision:** `llm_audit` ships as a pure Django app with management commands only. It adds zero
migrations, zero models, and zero database tables to the user's project.

**Why:** The plugin's job is to *read* the user's data and send it to an LLM. It has no reason
to own any schema. Adding migrations is the #1 reason developers hesitate to install third-party
Django packages — it's a commitment. We eliminate that friction entirely.

**Tradeoffs:**
- ✅ Zero DB footprint, easy to uninstall
- ✅ Works with any Django project regardless of DB engine
- ❌ Cannot persist summaries to a database by default (addressed in M4 via file output + optional mixin)

---

### ADR-002: Pluggable LLM backend system

**Decision:** All LLM calls go through an abstract `BaseLLMBackend` class. Users configure which
backend to use via `settings.LLM_AUDIT["BACKEND"]`.

**Why:** Tying the library to a single provider (Anthropic, OpenAI, etc.) would make it useless
to anyone not using that provider. More importantly, it teaches a fundamental software design
principle: *depend on abstractions, not concretions* (Dependency Inversion Principle). This is the
exact same pattern Django uses for its cache backend, email backend, and storage backend.

**Tradeoffs:**
- ✅ Provider-agnostic; works with Claude, GPT-4, Gemini, Ollama
- ✅ Testable — swap real backend for a mock backend in tests
- ❌ Slightly more complexity upfront; requires understanding abstract base classes

**Interface contract (what every backend must implement):**
```python
class BaseLLMBackend:
    def complete(self, prompt: str) -> str: ...
    def stream(self, prompt: str) -> Generator[str, None, None]: ...
    def count_tokens(self, text: str) -> int: ...
```

---

### ADR-003: Demo app ships inside the repo, not as a separate project

**Decision:** A `demo/` directory at the repo root contains a full Django project with realistic
fake data. It is not installed as part of the plugin — it exists only for development, testing,
and showcasing.

**Why:** Demos need to be runnable in one command by anyone who clones the repo. Keeping demo and
plugin in the same repo eliminates the "where's the demo?" friction for contributors and readers.
This is also how many popular Django packages work (e.g., `django-rest-framework` ships with a
sandbox app).

**Tradeoffs:**
- ✅ One repo, immediately runnable demo
- ✅ Demo models inform plugin design naturally
- ❌ Repo size is slightly larger; need to ensure `demo/` is excluded from the published PyPI package

---

### ADR-004: Records are serialized to JSON before being sent to the LLM

**Decision:** `.values()` queryset → `json.dumps(..., default=str)` → included in prompt as a
JSON block.

**Why:** JSON is the most universally understood structured format for LLMs. It preserves field
names (which carry semantic meaning), handles nested structures reasonably, and is trivially
produced from Django querysets. The `default=str` handles `Decimal`, `datetime`, and `UUID`
types that aren't natively JSON-serializable — a common Django gotcha.

**Tradeoffs:**
- ✅ Simple, readable, LLM-friendly
- ✅ Field names give the LLM semantic context ("amount", "status", "created_at")
- ❌ Verbose for wide tables; can consume tokens quickly (addressed in M2 chunking)
- ❌ Nested relations not included by default (deliberate — `.values()` is flat and safe)

---

### ADR-005: Token-aware chunking over naive record-count limits

**Decision:** The chunker divides records based on estimated token count, not a fixed record
limit. Each chunk stays under a configurable token threshold.

**Why:** Token limits are the fundamental constraint of LLM APIs. A fixed `--limit 50` is
arbitrary and brittle — 50 records of a wide model may exceed context, while 50 narrow records
waste capacity. Understanding tokens is the most important mental model shift when going from
traditional programming to LLM programming.

**Tradeoffs:**
- ✅ Works correctly regardless of model width
- ✅ Maximizes how much data fits in each LLM call
- ❌ Requires a token estimation function (we use `len(text) // 4` as a fast approximation;
  exact counting requires the `tiktoken` library or Anthropic's token counting API)

---

### ADR-006: Structured output via Pydantic, not string parsing

**Decision:** When structured output is needed, we instruct the LLM to return JSON matching a
defined schema, then parse it with Pydantic.

**Why:** String parsing of LLM output (regex, `.split()`, etc.) is fragile. LLMs occasionally
deviate from instructed formats. Pydantic gives you: schema documentation, automatic validation,
meaningful error messages, and Python type safety. This is the industry standard pattern for
production LLM applications.

**Tradeoffs:**
- ✅ Type-safe, validated, predictable output
- ✅ Self-documenting schema doubles as prompt guidance
- ❌ Adds Pydantic as a dependency (acceptable — it's already a Django/FastAPI standard)
- ❌ LLM must be instructed carefully; occasional JSON parse failures require retry logic

---

### ADR-007: pyproject.toml only, no setup.py or setup.cfg

**Decision:** Packaging uses `pyproject.toml` with `hatchling` as the build backend.

**Why:** `setup.py` is legacy. `pyproject.toml` is the modern Python packaging standard (PEP 517,
PEP 518, PEP 621). `hatchling` is lightweight, well-documented, and used by major projects.
Learning this correctly from the start saves unlearning bad habits later.

**Tradeoffs:**
- ✅ Modern, standards-compliant, future-proof
- ✅ Single file for all project metadata
- ❌ Less Stack Overflow content for edge cases vs. `setup.py` (but official docs are excellent)

---

## 4. Repository Structure

```
django-llm-audit/
│
├── llm_audit/                          # The installable Django plugin
│   ├── __init__.py                     # Version string lives here: __version__ = "0.1.0"
│   ├── apps.py                         # AppConfig: name = "llm_audit"
│   ├── conf.py                         # Settings accessor (see §8)
│   ├── exceptions.py                   # Custom exceptions (LLMBackendError, ChunkingError, etc.)
│   ├── summarizer.py                   # Orchestration: takes records, returns SummaryReport
│   ├── chunker.py                      # Splits record lists into token-safe chunks
│   ├── serializer.py                   # Model → JSON string (extracted from summarizer in M2)
│   ├── prompts.py                      # All prompt templates live here, not inline in code
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── base.py                     # Abstract BaseLLMBackend
│   │   ├── anthropic.py                # Claude implementation
│   │   └── openai.py                   # OpenAI implementation (added in M5)
│   ├── management/
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       └── audit_model.py          # The management command
│   └── schemas/
│       ├── __init__.py
│       └── report.py                   # Pydantic models for structured output (added in M4)
│
├── demo/                               # Public demo Django project (NOT part of pip package)
│   ├── manage.py
│   ├── demo/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   └── urls.py
│   ├── store/                          # The demo app with e-commerce models
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── admin.py
│   │   └── management/
│   │       └── commands/
│   │           └── seed_data.py        # Generates realistic fake data
│   └── requirements.txt
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # pytest fixtures, mock backend, test Django settings
│   ├── test_chunker.py
│   ├── test_summarizer.py
│   ├── test_serializer.py
│   ├── test_backends.py
│   └── test_management_command.py
│
├── docs/
│   ├── index.md                        # MkDocs entry point
│   ├── getting-started.md
│   ├── configuration.md
│   ├── backends.md
│   └── changelog.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml                      # Run tests on every push/PR
│       └── publish.yml                 # Publish to PyPI on version tag
│
├── CLAUDE.md                           # This file
├── CHANGELOG.md                        # Human-readable release notes
├── CONTRIBUTING.md
├── LICENSE                             # MIT
├── README.md                           # The public face; written README-first in M6
├── pyproject.toml                      # All packaging metadata + tool config
└── .env.example                        # ANTHROPIC_API_KEY=your_key_here
```

### Why separate `llm_audit/` from `demo/`?

When you run `pip install django-llm-audit`, pip only installs `llm_audit/`. The `demo/` directory
is excluded via `pyproject.toml`. This is a critical distinction: your plugin code must never
import from `demo/`, but `demo/` freely imports from `llm_audit/`. This one-way dependency
enforces the plugin's independence.

---

## 5. The Demo App

### Domain: E-commerce store

An online store is the ideal demo domain because:
1. Universally understood — no domain knowledge required to read the output
2. Naturally varied data — products, orders, line items, refunds, statuses
3. Produces genuinely interesting LLM summaries ("23% refund rate in Electronics is anomalous")
4. Free of PII — everything is faker-generated
5. Demonstrates multiple model types: flat (Product), relational (OrderItem), time-series (Order)

### Models

```python
# demo/store/models.py

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self): return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        PAID      = "paid",      "Paid"
        SHIPPED   = "shipped",   "Shipped"
        DELIVERED = "delivered", "Delivered"
        REFUNDED  = "refunded",  "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    customer_email = models.EmailField()      # fake email from Faker — no real PII
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Order #{self.pk} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self): return self.quantity * self.unit_price
```

### Seed data strategy

The `seed_data` management command generates:
- 8 categories
- ~80 products with realistic names and price ranges per category
- ~300 orders spread over 12 months, with realistic status distributions
- ~600 order items (avg 2 items per order)
- Intentional anomalies baked in (a category with high refund rate, a product always out of stock,
  a spike in orders in one month) — so the LLM summaries are *interesting*

Seeding uses the `faker` library. The command is idempotent (safe to run multiple times) and
accepts a `--reset` flag to wipe and reseed.

```bash
python demo/manage.py seed_data          # seed once
python demo/manage.py seed_data --reset  # wipe and reseed
```

---

## 6. The Plugin (`llm_audit`)

### Management command interface

The primary surface area of the plugin is a single management command: `audit_model`.

```
python manage.py audit_model
    --app       <app_label>         # Django app label (required if model name is ambiguous)
    --model     <ModelName>         # Django model class name (required)
    --limit     <int>               # Max records (default: 50)
    --fields    <f1,f2,f3>          # Comma-separated field names to include (default: all)
    --filter    <json>              # JSON-encoded queryset filter, e.g. '{"status":"paid"}'
    --output    <path>              # Save report to file (default: stdout)
    --format    text|json|markdown  # Output format (default: text)
    --stream                        # Stream output token-by-token (default: False)
    --backend   <dotted.path>       # Override configured backend for this run
```

**Why `--fields`?** Wide models with many columns waste tokens on irrelevant data. If you only
care about `status`, `total`, and `created_at`, there's no reason to send `updated_at`,
`internal_notes`, etc. to the LLM.

**Why `--filter`?** You often want summaries of a subset — "summarize only paid orders from Q4".
Accepting a JSON filter keeps the interface simple without inventing a custom query language.

**Why `--format`?** Different use cases need different outputs. `text` for humans reading in
terminal. `json` for piping into scripts. `markdown` for pasting into Notion/Confluence reports.

### Data flow (overview)

```
Management Command
    │
    ├── resolve model class from --app / --model
    ├── build queryset (apply --filter, --fields, --limit)
    │
    ▼
Serializer
    │
    ├── .values(*fields) → list of dicts
    ├── json.dumps(default=str) → JSON string
    ▼
Chunker
    │
    ├── estimate token count of full JSON
    ├── if fits in one chunk → single chunk
    └── else → split into N chunks, each under token threshold
        │
        ▼
Summarizer
    │
    ├── for each chunk: build_prompt(chunk) → call backend.complete() → chunk_summary
    ├── if multiple chunks: build_meta_prompt(chunk_summaries) → final_summary
    │
    ▼
Output formatter (text / json / markdown)
    │
    ▼
stdout or file
```

### Prompt design

All prompt templates live in `llm_audit/prompts.py`. They are never hardcoded inline in
`summarizer.py` or the management command. This makes them easy to find, read, review, and
eventually override (M5+).

The base prompt structure:

```
[System context]
You are a data analyst reviewing database records from a Django application.
Be specific and concrete. Reference actual values. Do not speculate beyond the data.

[Task]
Analyze the following {record_count} records from the '{model_name}' table.

Provide:
1. A one-sentence headline insight
2. Key patterns and trends (3-5 bullet points)
3. Anomalies or values that seem unusual
4. A brief overall assessment (2-3 sentences)

[Data]
{records_json}
```

**Why explicit output structure in the prompt?** Without it, LLMs return inconsistently formatted
prose that's hard to parse or display cleanly. Asking for numbered sections gives predictable,
scannable output. This is the precursor to the full structured JSON output in M4.

---

## 7. LLM Design Principles

These principles apply to every LLM interaction in this codebase. Learn them here; they apply
everywhere in AI engineering.

### Tokens are the unit of cost and constraint

Every character you send to an LLM costs money and consumes finite context space. Always ask:
"What is the minimum information needed for the LLM to do this task well?"

This drives: `--fields` filtering, `--limit`, chunking, and prompt brevity.

### Prompt templates are code

Prompts are not strings you tweak casually. They are the primary logic of your application.
Changes to prompts change application behaviour. They should be:
- Version controlled (they are, in `prompts.py`)
- Reviewed with the same care as code changes
- Tested (with eval scripts in later milestones)

### Ground the LLM in your data

Generic prompts get generic answers. Giving the LLM: the model name, field names (which carry
semantic meaning), and actual values produces dramatically better analysis than sending anonymous
column data. Always tell the LLM what it's looking at.

### Never trust LLM output blindly

In M4, when we ask for structured JSON output, we always validate with Pydantic. We never
`json.loads()` raw LLM output without a try/except. We implement retry logic for malformed
responses. This is not pessimism — it's production engineering.

### Streaming is UX, not just performance

A 10-second blocking call feels broken. The same 10-second operation that starts printing tokens
after 200ms feels responsive. Always expose streaming as an option for operations that take more
than ~2 seconds. The cost is trivial; the UX improvement is significant.

---

## 8. Configuration System

### Settings pattern

The plugin reads its configuration from `settings.LLM_AUDIT` (a dict), with sensible defaults.
This mirrors how `django-allauth`, `django-rest-framework`, and other well-designed Django plugins
handle configuration.

```python
# In user's settings.py
LLM_AUDIT = {
    "BACKEND": "llm_audit.backends.anthropic.AnthropicBackend",
    "API_KEY": env("ANTHROPIC_API_KEY"),
    "MODEL": "claude-opus-4-5",          # LLM model name
    "MAX_TOKENS": 1024,                  # Max tokens in LLM response
    "CHUNK_TOKEN_THRESHOLD": 3000,       # Max tokens per chunk sent to LLM
    "DEFAULT_RECORD_LIMIT": 50,          # Default --limit if not specified
}
```

### Settings accessor (`conf.py`)

We never call `settings.LLM_AUDIT["KEY"]` directly in plugin code. Instead, we use a settings
accessor object that:
1. Provides defaults (so users don't need to specify every key)
2. Raises clear errors for missing required keys
3. Gives one place to look for all configuration

```python
# llm_audit/conf.py
from django.conf import settings

DEFAULTS = {
    "MODEL": "claude-opus-4-5",
    "MAX_TOKENS": 1024,
    "CHUNK_TOKEN_THRESHOLD": 3000,
    "DEFAULT_RECORD_LIMIT": 50,
}

class LLMAuditSettings:
    def __getattr__(self, name):
        user_settings = getattr(settings, "LLM_AUDIT", {})
        if name in user_settings:
            return user_settings[name]
        if name in DEFAULTS:
            return DEFAULTS[name]
        raise AttributeError(f"Invalid LLM_AUDIT setting: '{name}'")

audit_settings = LLMAuditSettings()
```

**Why not just `getattr(settings, "LLM_AUDIT", {})`?** Because scattered `settings.LLM_AUDIT.get()`
calls throughout the codebase are hard to find, don't validate, and don't provide defaults
consistently. The settings accessor pattern is the Django way.

### Named backends (added post-M5)

The flat shape above configures one provider. To switch between several in one run, `LLM_AUDIT`
also accepts a `BACKENDS` dict of self-contained bundles plus a `DEFAULT` — the same pattern as
Django's `DATABASES` + `--database`:

```python
LLM_AUDIT = {
    "DEFAULT": "anthropic",
    "BACKENDS": {
        "anthropic": {"BACKEND": "anthropic", "API_KEY": env("ANTHROPIC_API_KEY"), "MODEL": "claude-..."},
        "openai":    {"BACKEND": "openai",    "API_KEY": env("OPENAI_API_KEY"),    "MODEL": "gpt-4o"},
        "ollama":    {"BACKEND": "ollama",    "MODEL": "llama3.1"},   # local, no key
    },
    "MAX_TOKENS": 1024,            # shared; may be overridden per bundle
    "CHUNK_TOKEN_THRESHOLD": 3000, # pipeline-wide (never per-backend)
    "DEFAULT_RECORD_LIMIT": 50,    # pipeline-wide
}
```

Each bundle **requires** its own `BACKEND` (an alias or dotted path); `API_KEY`/`MODEL` are
per bundle; `MAX_TOKENS` resolves per bundle → top-level → default. `--backend <name>` selects
a whole bundle (class **and** key **and** model), which is what makes a one-run provider switch
actually work — the original flat-mode `--backend` swapped only the class while key/model stayed
global, so it could not switch between two real cloud providers.

`conf.resolve_backend_config(name)` hides both shapes from callers and is the *only* place that
reads per-backend config; `audit_settings` still serves the pipeline-wide keys. Invalid config
(unknown name, `BACKENDS` without `DEFAULT`, a bundle missing `BACKEND`) raises
`ImproperlyConfigured`, surfaced by the command as a clean `CommandError`. The flat shape
remains fully supported for the single-provider case.

`BACKEND` aliases (`anthropic`/`openai`/`ollama`/`mock`) are accepted anywhere a `BACKEND` value
is expected, in both shapes (`backends.BACKEND_ALIASES`).

---

## 9. Complete Milestone Roadmap

Each milestone is self-contained: it introduces new concepts, produces working code, and ends with
something you can show or commit.

---

### M0 — Repo scaffolding & demo app
**Goal:** Runnable skeleton. `python demo/manage.py seed_data` works.

**What you'll do:**
- Create GitHub repo, add MIT license, initial README placeholder
- Set up `pyproject.toml` with `hatchling`
- Create `llm_audit/` package skeleton (empty files, correct structure)
- Create `demo/` Django project with `store` app and models
- Write `seed_data` management command using `faker`
- Set up `pytest` with a Django test settings file
- Set up `pre-commit` with `ruff` (linter) and `black` (formatter)

**Concepts introduced:**
- Modern Python packaging (`pyproject.toml`, `hatchling`)
- `pre-commit` hooks for code quality
- Django app structure vs. Django project structure
- The difference between dev dependencies and runtime dependencies
- `faker` for realistic test data

**Deliverable:** Repo on GitHub, README with badges, `seed_data` working, CI green.

---

### M1 — Bare LLM call (no abstraction)
**Goal:** The simplest possible working command. Feel the API directly.

**What you'll do:**
- Add `anthropic` to dependencies
- Implement `audit_model` command: queryset → `.values()` → JSON → raw Anthropic API call → print
- No chunking, no streaming, no abstraction — just the raw call
- Hard-code the model to `store.Order` for now

**Concepts introduced:**
- Anthropic SDK: `client.messages.create()`, message format, response structure
- Prompt construction: system prompt vs. user message, why both matter
- `json.dumps(default=str)`: why this is needed with Django querysets
- Token cost intuition: run the same command with `--limit 5`, `--limit 20`, `--limit 50`
  and observe the response time and output quality difference
- Django management command internals: `BaseCommand`, `add_arguments`, `handle`, `self.stdout`

**Learning exercise:** After it works, intentionally break it in three ways and understand each
error: (a) send 500 records and watch it fail or slow down, (b) remove `default=str` and see the
serialization error, (c) send an empty queryset and handle that gracefully.

**Deliverable:** `python demo/manage.py audit_model` prints a summary of Order records.

---

### M2 — Token-aware chunking
**Goal:** Handle arbitrarily large record sets correctly.

**What you'll do:**
- Extract `serializer.py` from M1's inline code
- Write `chunker.py`: takes a list of records + token threshold → yields lists of records
- Implement the "summarize chunks, then summarize summaries" pattern in `summarizer.py`
- Wire `--limit` as a safety cap, not the primary constraint

**Concepts introduced:**
- What tokens are: roughly 4 characters per token (English text); why this approximation works
  well enough and when to use exact counting
- Chunking strategies: by token count vs. by record count vs. by semantic boundary (we use
  token count — most principled for this use case)
- The "map-reduce" pattern for LLMs: a classic technique used in summarization, RAG, and agents
- Why LLM context windows matter and how to think about them as a resource

**Learning exercise:** Observe what happens to summary quality as chunks get smaller (more chunks,
less context per chunk = potentially less coherent overall summary). This is a real tension in
production RAG systems.

**Deliverable:** `audit_model` works correctly on 500+ records without errors.

---

### M3 — Streaming output
**Goal:** Responsive UX for slow operations; understand async LLM patterns.

**What you'll do:**
- Add `--stream` flag to `audit_model`
- Implement `backend.stream()` using Anthropic's streaming API (`client.messages.stream`)
- Print tokens to stdout as they arrive using a generator pattern
- Handle the streaming/non-streaming distinction cleanly in `summarizer.py`

**Concepts introduced:**
- Server-sent events (SSE): what streaming actually is at the HTTP level
- Python generators (`yield`): how streaming maps naturally to generator functions
- Why streaming matters for UX even when total time is the same
- The tradeoff: streaming makes it harder to post-process the full response (you don't have it
  until the stream ends). This foreshadows the structured output problem in M4.

**Learning exercise:** Implement a simple token counter that displays "X tokens received" as
the stream runs. This builds intuition for LLM response sizes.

**Deliverable:** `python demo/manage.py audit_model --stream` prints tokens as they arrive.

---

### M4 — Structured output with Pydantic
**Goal:** Replace free-text output with a validated, typed data structure.

**What you'll do:**
- Add `pydantic` to dependencies
- Define `SummaryReport` in `llm_audit/schemas/report.py`
- Update the prompt to request JSON output matching the schema
- Parse and validate the LLM response with Pydantic
- Implement retry logic (up to 2 retries) for malformed JSON
- Add `--format json` and `--format markdown` output options
- Add `--output <path>` to save reports to disk

**The schema:**
```python
class Anomaly(BaseModel):
    field: str
    description: str
    severity: Literal["low", "medium", "high"]

class SummaryReport(BaseModel):
    model_name: str
    record_count: int
    headline: str                    # one-sentence key insight
    patterns: list[str]              # 3-5 bullet points
    anomalies: list[Anomaly]         # structured anomaly list
    assessment: str                  # 2-3 sentence overall assessment
    generated_at: datetime
```

**Concepts introduced:**
- Structured outputs: the industry-standard way to get reliable data from LLMs
- Pydantic v2: model definition, validation, `model_validate`, error handling
- JSON mode prompting: how to instruct an LLM to return only JSON
- Retry patterns: why LLMs occasionally produce invalid JSON and how to handle it gracefully
- Why structured output is the foundation of every AI product feature

**Learning exercise:** Deliberately ask for a field the LLM often gets wrong (e.g., a strict enum)
and observe how often it fails. This builds intuition for prompt engineering.

**Deliverable:** `audit_model --format json` outputs a validated JSON report every time.

---

### M5 — Pluggable LLM backends
**Goal:** Make the plugin provider-agnostic. Learn dependency inversion.

**What you'll do:**
- Define `BaseLLMBackend` abstract class in `backends/base.py`
- Refactor `AnthropicBackend` to implement this interface
- Implement `OpenAIBackend` (requires `openai` as an optional dependency)
- Implement `MockBackend` for testing (returns deterministic fake summaries)
- Wire backend selection through `conf.py` settings
- Document how to write a custom backend (for Ollama, Gemini, etc.)

**Concepts introduced:**
- Abstract Base Classes (`abc.ABC`, `@abstractmethod`): Python's mechanism for defining interfaces
- Dependency Inversion Principle: the plugin depends on the abstraction, not the implementation
- Optional dependencies in `pyproject.toml`: `pip install django-llm-audit[openai]`
- How Django itself uses this pattern (email backend, cache backend, storage backend)

**Learning exercise:** Write a `OllamaBackend` that calls a local Ollama instance. This teaches
you how to work with LLM providers that don't have official SDKs — just an HTTP API.

**Deliverable:** Plugin works identically with `AnthropicBackend` and `OpenAIBackend`.

---

### M6 — Tests & CI
**Goal:** Proper test coverage. CI that blocks broken PRs.

**What you'll do:**
- Write unit tests for `chunker.py` (pure functions, no LLM needed)
- Write unit tests for `serializer.py`
- Write integration tests for `summarizer.py` using `MockBackend`
- Write management command tests using Django's `call_command`
- Set up GitHub Actions CI: run tests on push and PRs, across Python 3.10/3.11/3.12
- Add a coverage badge to README

**Concepts introduced:**
- Why you test LLM applications differently from regular applications (you mock the LLM, not the
  data — the LLM is an external I/O dependency like a database)
- `pytest-django`: Django-aware pytest fixtures (`db`, `settings`, etc.)
- `call_command` for testing management commands
- GitHub Actions: workflow syntax, matrix builds, caching pip dependencies
- Coverage reports: what to measure and what not to obsess over

**Deliverable:** `pytest` passes with >80% coverage. CI green on GitHub.

---

### M7 — README-driven documentation
**Goal:** Documentation good enough that a stranger can use the plugin.

**What you'll do:**
- Write the full README.md: installation, quickstart, all CLI flags, configuration reference,
  backend guide, "writing a custom backend" section
- Write `CHANGELOG.md` (retroactively for all milestones, following Keep a Changelog format)
- Write `CONTRIBUTING.md`
- Set up MkDocs with Material theme for hosted docs (optional but impressive)

**Why README-first?** Writing documentation forces you to use your own API as a stranger would.
Every awkward sentence in the docs is a design smell in the code. This is the best QA pass you
can do before launch.

**Deliverable:** README is the first thing you'd want to read if you discovered this on GitHub.

---

### M8 — PyPI launch
**Goal:** `pip install django-llm-audit` works.

**What you'll do:**
- Finalize `pyproject.toml`: classifiers, URLs, keywords, Python version constraints
- Verify `demo/` is excluded from the built package
- Publish to TestPyPI first: `python -m build && twine upload --repository testpypi dist/*`
- Install from TestPyPI and verify it works in a fresh virtualenv
- Set up GitHub Actions `publish.yml`: triggers on `v*` tag push → builds → uploads to PyPI
- Tag `v0.1.0`, push, watch the workflow publish
- Announce: GitHub release notes, a blog post or Twitter/X thread, add to your portfolio

**Concepts introduced:**
- `python -m build`: creating sdist and wheel
- TestPyPI: the staging environment for PyPI (use it; it's free)
- Trusted publishing: GitHub Actions → PyPI OIDC (the modern, password-free publish method)
- Semantic versioning: why `0.1.0` is correct for a first public release
- GitHub Releases: tagging, release notes, changelogs

**Deliverable:** `pip install django-llm-audit` installs a working plugin from PyPI.

---

## 10. Packaging & Release Strategy

### Version scheme

Follows Semantic Versioning (`MAJOR.MINOR.PATCH`):
- `0.x.x` — pre-stable; public API may change
- `1.0.0` — stable public API commitment (after M8 + real-world feedback)

Version string lives in exactly one place: `llm_audit/__init__.py` as `__version__ = "0.1.0"`.
`pyproject.toml` references it dynamically:

```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "llm_audit/__init__.py"
```

### What goes on PyPI

Only the `llm_audit/` package. Explicitly excluded from the built package:
- `demo/`
- `tests/`
- `docs/`
- `CLAUDE.md`

### Dependency philosophy

Runtime dependencies (in `[project] dependencies`) must be minimal:
- `Django>=4.2` (we support the two current LTS versions)
- `pydantic>=2.0`

LLM SDKs are optional extras:
- `pip install django-llm-audit[anthropic]` → installs `anthropic`
- `pip install django-llm-audit[openai]` → installs `openai`
- `pip install django-llm-audit[all]` → installs both

**Why optional?** A user who only uses OpenAI should not be forced to install the Anthropic SDK.
Keeping runtime deps minimal is a sign of a well-designed library.

---

## 11. Testing Strategy

### What to test and what not to test

**Test:**
- `chunker.py`: pure functions, no external dependencies. 100% coverage expected.
- `serializer.py`: Django ORM → JSON. Use `pytest-django` and test models.
- `summarizer.py`: use `MockBackend`. Test the orchestration logic, not the LLM.
- Management command: use `call_command`, assert stdout/file output.
- Settings accessor: test defaults, overrides, and missing required keys.
- Pydantic schemas: test validation success and failure cases.

**Do not test:**
- The actual LLM response quality (that's evals, not unit tests)
- The Anthropic/OpenAI SDKs themselves (not our code)
- Django's ORM behaviour (Django tests that itself)

### Testing the LLM layer

The `MockBackend` returns a hardcoded `SummaryReport` JSON string regardless of input. This lets
you test everything around the LLM call (chunking, prompt building, output formatting, retry
logic) without making real API calls in CI.

For manual quality evaluation, maintain a `scripts/eval.py` script that runs the real backend
against the seeded demo data and prints results. Run this manually before releases.

### Test file conventions

- One test file per source file: `chunker.py` → `test_chunker.py`
- Test function names describe behaviour: `test_chunker_splits_on_token_threshold`
- Fixtures in `conftest.py`: `mock_backend`, `seeded_db`, `test_settings`

---

## 12. Documentation Strategy

### README structure (final form after M7)

```
1. What it does (2 sentences + example output screenshot)
2. Installation
3. Quickstart (copy-paste working example)
4. Configuration reference (table of all LLM_AUDIT settings)
5. CLI reference (all flags with examples)
6. Backends (built-in backends + writing a custom one)
7. Output formats (text, json, markdown examples)
8. Contributing
9. License
```

### Changelog format

Follows [Keep a Changelog](https://keepachangelog.com) format. Updated with every milestone.
Sections per release: `Added`, `Changed`, `Fixed`, `Removed`.

---

## 13. Building in Public

### GitHub

- Commit after every logical unit of work (not just milestones)
- Write meaningful commit messages: `feat: add token-aware chunker` not `update code`
- Use GitHub Issues to track the milestone tasks — one issue per task
- Tag milestone completions: `git tag m1-bare-llm-call`

### Writing / social

Each milestone completion is a blog post or thread opportunity:

| Milestone | Post idea |
|-----------|-----------|
| M0 | "How I structure a Django plugin from scratch (with pyproject.toml)" |
| M1 | "My first raw Anthropic API call in Django — what I learned" |
| M2 | "Tokens are the new bytes: building a token-aware chunker" |
| M3 | "Streaming LLM output in a Django management command" |
| M4 | "Structured output from LLMs with Pydantic — the right way" |
| M5 | "How Django's backend pattern applies to LLM provider abstraction" |
| M8 | "I shipped my first PyPI package — here's everything I did" |

These posts compound: each one demonstrates a specific, teachable skill and drives traffic to
the project.

---

## 14. Conventions & Code Style

### Python style

- Formatter: `black` (line length 100)
- Linter: `ruff` (replaces flake8, isort, pyupgrade)
- Type hints: required on all public functions
- Docstrings: Google style, on all public classes and functions

### Commit message format

```
<type>: <short description>

Types: feat, fix, docs, test, refactor, chore, style
```

Examples:
- `feat: add --stream flag to audit_model command`
- `fix: handle empty queryset gracefully in serializer`
- `docs: add backend configuration guide to README`
- `test: add chunker unit tests for edge cases`

### Django conventions

- Settings accessed only through `conf.py` accessor, never `settings.LLM_AUDIT["key"]` directly
- Management command output: use `self.stdout.write()` with `self.style.SUCCESS/ERROR/WARNING`
- Never `print()` in plugin code (breaks capture in tests)

### File naming

- All lowercase, underscores: `audit_model.py`, `test_chunker.py`
- No abbreviations: `serializer.py` not `ser.py`, `exceptions.py` not `exc.py`

---

## 15. Decisions Log

A running record of decisions made and why. Add to this as the project evolves.

| Date | Decision | Reasoning |
|------|----------|-----------|
| 2026-06-03 | Use e-commerce domain for demo | Universal, interesting data, PII-free |
| 2026-06-03 | Zero migrations policy | Reduce install friction, no schema ownership |
| 2026-06-03 | Pydantic for structured output | Type safety, validation, industry standard |
| 2026-06-03 | Optional LLM SDK dependencies | Don't force Anthropic on OpenAI users |
| 2026-06-03 | `hatchling` as build backend | Modern, well-documented, no legacy baggage |
| 2026-06-03 | `prompts.py` for all templates | Prompts are code; they need to be findable |
| 2026-06-03 | MockBackend for CI tests | LLM quality is not unit-testable; mock the I/O |
| 2026-06-06 | Local backend = native Ollama over stdlib HTTP | M5 exercise: a provider with no SDK; zero new deps; teaches raw HTTP/NDJSON |
| 2026-06-06 | Short backend aliases (`anthropic`/`openai`/`ollama`/`mock`) | Lower wiring than dotted paths; non-aliases still resolve as paths so custom backends work |
| 2026-06-06 | Named backend configs (`BACKENDS`+`DEFAULT`) | Flat `--backend` swapped only the class while key/model stayed global, so it couldn't switch real providers; named bundles (Django `DATABASES` pattern) fix it. Flat shape kept for back-compat. Bundle `BACKEND` required (no name-as-alias inference — explicit over magic) |
| 2026-06-06 | M6: dedicated test app (`tests/testapp`) for integration tests | Need a real model with records to drive `call_command` end-to-end; reusing `demo/store` would couple the suite to the demo (breaks the one-way demo→plugin dependency). Migration-less app, table built via `--run-syncdb`. Canonical reusable-app testing pattern (DRF/allauth) |
| 2026-06-06 | M6: coverage gated at >80% in CI + Codecov badge | M6 deliverable is >80%. `--cov-fail-under=80` enforces it; real-SDK backend bodies stay untested (§11) and set the ceiling. Codecov gives a live README badge (tokenless for the public repo) |
| 2026-06-06 | M6: kept bespoke fakes in `test_summarizer`, used `MockBackend` only for command tests | The summarizer fakes introspect call order/system prompts and simulate retry-then-fail — `MockBackend` (deterministic, no call log) can't. MockBackend is right for end-to-end command output assertions |

---

*This file is the source of truth. When in doubt, re-read it.*
*When a decision here turns out to be wrong, update it and log why in §15.*