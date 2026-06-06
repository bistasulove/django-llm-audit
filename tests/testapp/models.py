"""Test-only models.

A deliberately tiny stand-in for the demo's ``Order``: just enough fields to exercise the
real path the plugin cares about — ``.values()`` over a model whose columns include the JSON
"gotcha" types (``Decimal``, ``datetime``) that the serializer's ``default=str`` exists to
handle (ADR-004). Keeping it minimal keeps the integration tests fast and readable.

No migrations: pytest-django builds the table with ``--run-syncdb`` (see ``apps.py``).
"""

from django.db import models


class Order(models.Model):
    """A minimal order, mirroring the demo's shape closely enough to be recognizable."""

    status = models.CharField(max_length=20, default="pending")
    total = models.DecimalField(max_digits=10, decimal_places=2)
    customer_email = models.EmailField()
    created_at = models.DateTimeField()

    class Meta:
        app_label = "testapp"

    def __str__(self):
        return f"Order #{self.pk} ({self.status})"
