"""The ``audit_model`` management command.

Implemented in M1. Resolves a Django model from ``--app``/``--model``, builds a
queryset, serializes it, and produces an LLM summary. This is the plugin's primary
surface area; for now it is a stub so the command registers and the help text renders.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Audit a Django model with an LLM (stub — implemented in M1)."""

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
        self.stdout.write(
            self.style.WARNING("audit_model is not implemented yet — arrives in milestone M1.")
        )
