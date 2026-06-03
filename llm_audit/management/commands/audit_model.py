"""The ``audit_model`` management command.

Implemented in M1. Resolves a Django model from ``--app``/``--model``, builds a
queryset, serializes it, and produces an LLM summary. This is the plugin's primary
surface area.

M1 is deliberately bare: no chunking (M2), no streaming (M3), no structured output
(M4), no backend abstraction (M5). Serialization is done inline here and extracted to
``serializer.py`` in M2. The ``--fields``, ``--filter``, ``--output``, ``--format``,
``--stream``, and ``--backend`` flags are parsed but not yet honored.
"""

import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from llm_audit.backends.anthropic import AnthropicBackend
from llm_audit.conf import audit_settings
from llm_audit.exceptions import LLMBackendError
from llm_audit.prompts import build_audit_prompt

#: M1 defaults when --app/--model are omitted. The demo's flagship time-series model.
DEFAULT_APP = "store"
DEFAULT_MODEL = "Order"


class Command(BaseCommand):
    """Audit a Django model with an LLM."""

    help = "Generate an LLM-powered summary of a Django model's records."

    def add_arguments(self, parser):
        parser.add_argument("--app", help="Django app label.")
        parser.add_argument("--model", help="Django model class name.")
        parser.add_argument("--limit", type=int, help="Max records to include.")
        parser.add_argument("--fields", help="Comma-separated field names to include.")
        parser.add_argument("--filter", help="JSON-encoded queryset filter.")
        parser.add_argument("--output", help="Save report to a file path.")
        parser.add_argument(
            "--format",
            choices=["text", "json", "markdown"],
            default="text",
            help="Output format.",
        )
        parser.add_argument("--stream", action="store_true", help="Stream output token-by-token.")
        parser.add_argument("--backend", help="Override the configured backend (dotted path).")

    def handle(self, *args, **options):
        app_label = options["app"] or DEFAULT_APP
        model_name = options["model"] or DEFAULT_MODEL

        # Resolve the model class from its app label + name. LookupError covers both an
        # unknown app and an unknown model; we turn it into a clean CommandError so the
        # user sees a one-line message, not a traceback.
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError as exc:
            raise CommandError(
                f"Could not resolve model '{app_label}.{model_name}': {exc}"
            ) from None

        limit = options["limit"] or audit_settings.DEFAULT_RECORD_LIMIT

        # .values() returns a list of dicts keyed by field name. Field names carry
        # semantic meaning ("status", "total", "created_at") that grounds the LLM.
        records = list(model.objects.values()[:limit])

        if not records:
            self.stdout.write(
                self.style.WARNING(f"No {model.__name__} records found. Nothing to audit.")
            )
            return

        # default=str is the crucial bit: Decimal, datetime, and UUID are not natively
        # JSON-serializable. Without it, json.dumps raises TypeError on the first
        # Decimal it meets. (Extracted to serializer.py in M2.)
        records_json = json.dumps(records, default=str, indent=2)

        # The keys of the first .values() dict are exactly the fields the model will
        # see. Passing them in lets the prompt tell the LLM what it has — and lacks.
        field_names = list(records[0].keys())

        system_prompt, user_prompt = build_audit_prompt(
            model_name=model.__name__,
            record_count=len(records),
            records_json=records_json,
            field_names=field_names,
        )

        self.stdout.write(
            self.style.NOTICE(
                f"Auditing {len(records)} {model.__name__} record(s) with "
                f"{audit_settings.MODEL}...\n"
            )
        )

        # Surface backend problems (missing key, missing SDK, API failure) as a clean
        # one-line CommandError rather than a traceback.
        try:
            backend = AnthropicBackend(
                api_key=audit_settings.API_KEY,
                model=audit_settings.MODEL,
                max_tokens=audit_settings.MAX_TOKENS,
            )
            summary = backend.complete(user_prompt, system=system_prompt)
        except LLMBackendError as exc:
            raise CommandError(str(exc)) from None

        self.stdout.write(summary)
