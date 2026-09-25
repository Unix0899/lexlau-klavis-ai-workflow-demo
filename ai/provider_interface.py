"""Provider abstraction.

    AIProvider
    |-- MockAIProvider          default, deterministic, no API key   (mock_provider.py)
    |-- MockFallbackProvider    simpler backup engine, no API key    (mock_provider.py)
    |-- OpenAIProvider          optional, env var                    (external_providers.py)
    `-- AnthropicProvider       optional, env var                    (external_providers.py)

Every provider returns the same output contract, checked by validate_extraction_output()
before anything is stored. A provider that breaks the contract is treated as a failure
and the fallback chain moves on (see fallback.py).

This is an independently written demo architecture; it does not reproduce the
architecture of Klavis.
"""
from abc import ABC, abstractmethod

from .config import CATEGORIES

TEXT_FIELDS = ("case_title", "case_reference", "client_name", "opposing_party",
               "document_type", "jurisdiction")
LIST_FIELDS = ("important_dates", "amounts")


class ProviderError(Exception):
    code = "PROVIDER_ERROR"

    def __init__(self, message="Provider error", code=None):
        super().__init__(message)
        if code:
            self.code = code


class ProviderTimeout(ProviderError):
    code = "PROVIDER_TIMEOUT"


class ProviderUnavailable(ProviderError):
    code = "PROVIDER_UNAVAILABLE"


class InvalidProviderOutput(ProviderError):
    code = "INVALID_OUTPUT"


class AIProvider(ABC):
    """Interface every provider implements."""

    name = "abstract"
    is_external = False

    @abstractmethod
    def extract(self, text: str, simulate_failure: str | None = None) -> dict:
        """Return {"fields": {name: {"value", "confidence", "method"}}, "conflicts": [...]}."""

    @abstractmethod
    def suggest_category(self, text: str, simulate_failure: str | None = None) -> dict:
        """Return {"category", "confidence", "scores": {category: score}}."""

    @abstractmethod
    def summarise(self, case: dict, simulate_failure: str | None = None) -> str:
        """Short summary built from the *structured* case fields (not the raw document)."""

    @abstractmethod
    def answer(self, question: str, case: dict, simulate_failure: str | None = None) -> str:
        """Answer a question about the current synthetic case (structured fields only)."""


def validate_extraction_output(out) -> dict:
    """Reject anything that does not follow the contract. Raises InvalidProviderOutput."""
    if not isinstance(out, dict) or not isinstance(out.get("fields"), dict):
        raise InvalidProviderOutput("Output is not an object with a 'fields' object")
    fields = out["fields"]
    for name in TEXT_FIELDS + LIST_FIELDS:
        f = fields.get(name)
        if not isinstance(f, dict) or "value" not in f:
            raise InvalidProviderOutput(f"Field '{name}' missing from output")
        conf = f.get("confidence")
        if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            raise InvalidProviderOutput(f"Field '{name}' has an invalid confidence")
        v = f["value"]
        if name in TEXT_FIELDS and v is not None and not isinstance(v, str):
            raise InvalidProviderOutput(f"Field '{name}' must be a string or null")
        if name in LIST_FIELDS and not isinstance(v, list):
            raise InvalidProviderOutput(f"Field '{name}' must be a list")
    for d in fields["important_dates"]["value"]:
        if not isinstance(d, dict) or "label" not in d or "date" not in d:
            raise InvalidProviderOutput("Malformed date entry")
    for a in fields["amounts"]["value"]:
        if not isinstance(a, dict) or "label" not in a or "value" not in a:
            raise InvalidProviderOutput("Malformed amount entry")
        if a["value"] is not None and not isinstance(a["value"], (int, float)):
            raise InvalidProviderOutput("Amount value must be numeric or null")
    if not isinstance(out.get("conflicts", []), list):
        raise InvalidProviderOutput("'conflicts' must be a list")
    out.setdefault("conflicts", [])
    return out


def validate_category_output(out) -> dict:
    if not isinstance(out, dict) or out.get("category") not in CATEGORIES:
        raise InvalidProviderOutput("Category outside the taxonomy")
    if not isinstance(out.get("confidence"), (int, float)) or not 0 <= out["confidence"] <= 1:
        raise InvalidProviderOutput("Invalid category confidence")
    out.setdefault("scores", {})
    return out
