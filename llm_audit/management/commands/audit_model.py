"""The ``audit_model`` management command.

Implemented in M1. Resolves a Django model from ``--app``/``--model``, builds a
queryset, serializes it, and produces an LLM summary. This is the plugin's primary
surface area.

As of M2 the command resolves the model and pulls records, then hands off to
``summarizer.summarize``, which chunks the data (token-aware) and runs the map-reduce
summarization. Serialization moved to ``serializer.py`` and chunking to ``chunker.py``.

Still deferred: streaming (M3), structured output (M4), backend abstraction (M5). The
``--fields``, ``--filter``, ``--output``, ``--format``, ``--stream``, and ``--backend``
flags are parsed but not yet honored.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from llm_audit import summarizer
from llm_audit.backends.anthropic import AnthropicBackend
from llm_audit.conf import audit_settings
from llm_audit.exceptions import LLMBackendError

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

        self.stdout.write(
            self.style.NOTICE(
                f"Auditing {len(records)} {model.__name__} record(s) with "
                f"{audit_settings.MODEL}...\n"
            )
        )

        # Surface backend problems (missing key, missing SDK, API failure) as a clean
        # one-line CommandError rather than a traceback. Serialization, chunking, and the
        # map-reduce summarization now all live behind summarizer.summarize. We inject the
        # backend and a notify callback so the library reports progress through our styled
        # stdout without importing Django or owning the terminal itself.
        try:
            backend = AnthropicBackend(
                api_key=audit_settings.API_KEY,
                model=audit_settings.MODEL,
                max_tokens=audit_settings.MAX_TOKENS,
            )
            summary = summarizer.summarize(
                records,
                model_name=model.__name__,
                backend=backend,
                token_threshold=audit_settings.CHUNK_TOKEN_THRESHOLD,
                notify=lambda msg: self.stdout.write(self.style.NOTICE(msg)),
            )
        except LLMBackendError as exc:
            raise CommandError(str(exc)) from None

        self.stdout.write(summary)
