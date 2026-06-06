"""The ``audit_model`` management command.

Implemented in M1. Resolves a Django model from ``--app``/``--model``, builds a
queryset, serializes it, and produces an LLM summary. This is the plugin's primary
surface area.

As of M2 the command resolves the model and pulls records, then hands off to
``summarizer.summarize``, which chunks the data (token-aware) and runs the map-reduce
summarization. Serialization moved to ``serializer.py`` and chunking to ``chunker.py``.

M3 wires ``--stream``: when set, the final report is printed token-by-token as it
arrives instead of all at once.

M4 wires ``--format`` and ``--output``. ``--format text`` keeps the free-text prose path
(streamable, M1–M3). ``--format json`` / ``markdown`` switch to the *structured* path: the
LLM returns JSON, validated into a :class:`~llm_audit.schemas.report.SummaryReport`, then
rendered. Structured output must be buffered to validate, so ``--stream`` is ignored there.
``--output`` writes the rendered report to a file instead of stdout.

M5 wires the backend abstraction: the command no longer names a concrete backend. It calls
``get_backend(--backend)``, which resolves ``LLM_AUDIT['BACKEND']`` (or the ``--backend``
override) to a class and instantiates it. Swapping Anthropic for OpenAI is now a settings
change, not a code change.

Streaming is now the **default** for interactive prose output (``--format text`` to the
terminal): a blocking call that prints nothing feels broken (CLAUDE.md §7). Use ``--no-stream``
to opt out for scripting/piping. Streaming is automatically disabled where it cannot work —
the structured JSON path (must buffer to validate) and file output (no cursor to animate).
While the model is working, a whimsical "thinking" line fills the wait, so the previously
silent single-chunk case now speaks.

Still deferred: the ``--fields`` and ``--filter`` flags are parsed but not yet honored.
"""

import argparse
import random

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from llm_audit import formatters, summarizer
from llm_audit.backends import get_backend
from llm_audit.chunker import estimate_tokens
from llm_audit.conf import audit_settings
from llm_audit.exceptions import LLMBackendError, StructuredOutputError

#: Formats that take the structured (validated JSON) path rather than free-text prose.
STRUCTURED_FORMATS = frozenset({"json", "markdown"})

#: M1 defaults when --app/--model are omitted. The demo's flagship time-series model.
DEFAULT_APP = "store"
DEFAULT_MODEL = "Order"

#: Whimsical status lines shown while the model works, so the wait never sits silent. This is
#: pure presentation copy and lives in the command, not the library (the summarizer stays
#: stdout-free and reports facts through ``notify``).
THINKING_PHRASES = (
    "Cooking up the analysis",
    "Crunching the numbers",
    "Reading the records",
    "Spotting patterns",
    "Distilling insights",
    "Simmering the summary",
    "Connecting the dots",
    "Sifting through the data",
)


def thinking_phrase() -> str:
    """Return a random whimsical status line for the 'model is working' wait."""
    return random.choice(THINKING_PHRASES)


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
        # BooleanOptionalAction gives both --stream and --no-stream. default=None lets us tell
        # "the user explicitly chose" from "took the default" — needed so the structured-format
        # warning only fires when --stream was passed on purpose.
        parser.add_argument(
            "--stream",
            action=argparse.BooleanOptionalAction,
            default=None,
            help=(
                "Stream the report token-by-token. On by default for --format text to the "
                "terminal; use --no-stream to disable. Ignored for structured formats and "
                "file output, which must buffer."
            ),
        )
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

        output_format = options["format"]
        output_path = options["output"]
        structured = output_format in STRUCTURED_FORMATS

        # Decide whether to stream. The rule — "stream whenever it can" — lives in a pure
        # helper so it is unit-testable without a backend or a model. warn_ignored is True
        # only when the user explicitly passed --stream somewhere it cannot apply.
        stream, warn_ignored = self._resolve_stream(output_format, output_path, options["stream"])
        if warn_ignored:
            self.stdout.write(
                self.style.WARNING(
                    f"--stream is ignored with --format {output_format}; structured "
                    "output must be buffered to validate. Producing a full report."
                )
            )

        self.stdout.write(
            self.style.NOTICE(
                f"Auditing {len(records)} {model.__name__} record(s) with "
                f"{audit_settings.MODEL}...\n"
            )
        )

        # Surface backend and validation problems as a clean one-line CommandError rather
        # than a traceback. Serialization, chunking, and the map-reduce summarization all
        # live behind summarizer.summarize. We inject the backend and a notify callback so
        # the library reports progress through our styled stdout without owning the
        # terminal itself.
        #
        # The whole produce-and-emit block sits inside this try: when streaming, the API
        # call happens as we consume the generator; in the structured path, validation
        # failures (StructuredOutputError) surface during summarize(). Either can fail after
        # we've started, so both must be guarded here.
        try:
            # Resolve the configured backend (or the --backend override) to an instance. The
            # command never names a provider — that is the whole point of M5's abstraction.
            backend = get_backend(options["backend"])

            # A whimsical status line fills the wait while the model works. For a single-chunk
            # run this is the only progress shown before the report; multi-chunk runs add their
            # own per-chunk notices on top (from the summarizer's notify callback).
            self.stdout.write(self.style.NOTICE(f"{thinking_phrase()}...\n"))

            result = summarizer.summarize(
                records,
                model_name=model.__name__,
                backend=backend,
                token_threshold=audit_settings.CHUNK_TOKEN_THRESHOLD,
                notify=lambda msg: self.stdout.write(self.style.NOTICE(msg)),
                stream=stream,
                structured=structured,
            )

            if structured:
                # summarize() returned a validated SummaryReport; render it to the format.
                self._emit(formatters.render(result, output_format), output_path)
            elif stream and not output_path:
                # Live prose to the terminal, token by token.
                self._write_stream(result)
            elif stream:
                # Streaming requested but writing to a file: buffer the pieces, no live
                # effect (decision E) — a file has no cursor to animate.
                self._emit("".join(result), output_path)
            else:
                self._emit(result, output_path)
        except (LLMBackendError, StructuredOutputError, ImproperlyConfigured) as exc:
            raise CommandError(str(exc)) from None

    @staticmethod
    def _resolve_stream(output_format, output_path, explicit_stream):
        """Decide whether to stream, and whether to warn about an ignored ``--stream``.

        The policy is "stream whenever it can": interactive prose to the terminal streams by
        default; everything else buffers. ``explicit_stream`` is ``True`` (``--stream``),
        ``False`` (``--no-stream``), or ``None`` (neither flag given).

        Args:
            output_format: The ``--format`` value (``text``/``json``/``markdown``).
            output_path: The ``--output`` path, or ``None`` for stdout.
            explicit_stream: The tri-state ``--stream``/``--no-stream`` choice.

        Returns:
            ``(stream, warn_ignored)`` — whether to stream, and whether to warn that an
            explicit ``--stream`` was ignored.
        """
        if output_format in STRUCTURED_FORMATS:
            # Structured output must be buffered to validate the JSON. Warn only if the user
            # explicitly asked to stream — not when they merely left the new default on.
            return False, explicit_stream is True
        if output_path:
            # Writing to a file: there is no cursor to animate, so buffer. No warning — this
            # is the expected behaviour, not a dropped request (M4 decision E).
            return False, False
        # Interactive prose to the terminal: stream unless explicitly opted out with
        # --no-stream. None (default) and True (--stream) both stream.
        return explicit_stream is not False, False

    def _emit(self, content, output_path):
        """Write a finished report to ``output_path`` if given, else to stdout."""
        if output_path:
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.write(content)
            self.stdout.write(self.style.SUCCESS(f"Report written to {output_path}"))
        else:
            self.stdout.write(content)

    def _write_stream(self, tokens):
        """Print streamed report pieces as they arrive, then a token tally.

        Each piece is written with ``ending=""`` (otherwise Django's OutputWrapper would
        append a newline per write) and followed by an explicit ``flush()`` — without it
        the terminal buffers output and the live, token-by-token effect is lost.

        We count as the stream runs and print the tally once it finishes. A truly
        in-place live counter would fight the report text for the same line, so showing
        it at the end is the clean choice. The count is an estimate (the same ~4-chars-
        per-token heuristic as the chunker), enough to build intuition for response size.
        """
        pieces = []
        for token in tokens:
            self.stdout.write(token, ending="")
            self.stdout.flush()
            pieces.append(token)
        self.stdout.write("")  # final newline once the stream is exhausted

        approx_tokens = estimate_tokens("".join(pieces))
        self.stdout.write(self.style.NOTICE(f"(~{approx_tokens} tokens received)"))
