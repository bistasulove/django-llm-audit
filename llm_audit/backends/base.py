"""Abstract base class for LLM backends.

Formalized in M5. Every backend implements ``complete``, ``stream``, and
``count_tokens`` so the rest of the plugin depends on this abstraction, never on a
concrete provider SDK (Dependency Inversion Principle).
"""

from abc import ABC, abstractmethod
from collections.abc import Generator


class BaseLLMBackend(ABC):
    """Interface every LLM backend must implement."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return the full completion for ``prompt``."""

    @abstractmethod
    def stream(self, prompt: str) -> Generator[str, None, None]:
        """Yield completion tokens for ``prompt`` as they arrive."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return the token count of ``text``."""
