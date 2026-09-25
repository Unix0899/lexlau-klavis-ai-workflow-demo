"""Optional external providers (OFF by default).

They are only built when the matching environment variable is present. Keys are
read from the environment at call time and never written anywhere (not to logs,
not to the database). Without a key the provider raises ProviderUnavailable and
the chain falls back to the local mock engine, so the demo never needs a key.

Data minimisation: extraction sends the document text (truncated); summaries and
the assistant only send the *structured* fields, never the full document.
Only use external providers with the synthetic documents of this repository.

These prompts are generic and were written for this public demo.
"""
import json
import os
import urllib.error
import urllib.request

from .config import CATEGORIES, PROVIDER_TIMEOUT_S
from .provider_interface import (AIProvider, InvalidProviderOutput, ProviderError,
                                 ProviderTimeout, ProviderUnavailable)

MAX_CHARS = 12_000

EXTRACTION_INSTRUCTIONS = (
    "You extract structured information from a synthetic legal document for a demo. "
    "Return only JSON: {\"fields\": {name: {\"value\": ..., \"confidence\": 0-1, \"method\": \"llm\"}}, "
    "\"conflicts\": [{\"field\": name, \"values\": [...]}]}. Field names: case_title, case_reference, "
    "client_name, opposing_party, document_type, jurisdiction (strings or null), important_dates "
    "(list of {label, date (YYYY-MM-DD or null), raw, incomplete}), amounts (list of {label, value "
    "(number or null), currency, raw}). Use null when a value is absent; never invent values; report "
    "contradictory values in conflicts."
)


class _HTTPProvider(AIProvider):
    is_external = True
    env_key = ""

    def _key(self):
        value = os.environ.get(self.env_key, "").strip()
        if not value:
            raise ProviderUnavailable(f"{self.name}: {self.env_key} is not set")
        return value

    def _post(self, url, headers, body):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=PROVIDER_TIMEOUT_S) as resp:
                return json.loads(resp.read())
        except TimeoutError:
            raise ProviderTimeout(f"{self.name} timed out") from None
        except urllib.error.HTTPError as exc:
            # the status code is enough to diagnose; the response body is not logged
            raise ProviderError(f"{self.name} returned HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise ProviderError(f"{self.name} unreachable ({type(exc.reason).__name__})") from None

    def _complete(self, system, user):
        raise NotImplementedError

    def _json(self, system, user):
        raw = self._complete(system, user)
        try:
            start, end = raw.index("{"), raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except ValueError:
            raise InvalidProviderOutput(f"{self.name} did not return JSON") from None

    def extract(self, text, simulate_failure=None):
        return self._json(EXTRACTION_INSTRUCTIONS, text[:MAX_CHARS])

    def suggest_category(self, text, simulate_failure=None):
        return self._json(
            "Classify the synthetic legal document into exactly one category of: "
            + ", ".join(CATEGORIES)
            + ". Return only JSON {\"category\": ..., \"confidence\": 0-1, \"scores\": {}}.",
            text[:MAX_CHARS])

    def summarise(self, case, simulate_failure=None):
        return self._complete(
            "Write a neutral three-sentence summary of this synthetic case from its structured "
            "fields. Do not give legal advice. Mention missing information.",
            json.dumps(case, ensure_ascii=False))

    def answer(self, question, case, simulate_failure=None):
        return self._complete(
            "You are a demo assistant. Answer only from the structured fields of the synthetic case "
            "provided. Never give legal advice; say so if asked. Be brief.",
            json.dumps({"case": case, "question": question}, ensure_ascii=False))


class OpenAIProvider(_HTTPProvider):
    name = "openai"
    env_key = "OPENAI_API_KEY"

    def _complete(self, system, user):
        model = os.environ.get("LEXLAU_OPENAI_MODEL", "gpt-4o-mini")
        data = self._post(
            "https://api.openai.com/v1/chat/completions",
            {"Content-Type": "application/json", "Authorization": "Bearer " + self._key()},
            {"model": model, "temperature": 0,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise InvalidProviderOutput("Unexpected OpenAI response shape") from None


class AnthropicProvider(_HTTPProvider):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"

    def _complete(self, system, user):
        model = os.environ.get("LEXLAU_ANTHROPIC_MODEL", "claude-sonnet-5")
        data = self._post(
            "https://api.anthropic.com/v1/messages",
            {"Content-Type": "application/json", "x-api-key": self._key(),
             "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": 1500, "system": system,
             "messages": [{"role": "user", "content": user}]})
        try:
            return "".join(block.get("text", "") for block in data["content"])
        except (KeyError, TypeError):
            raise InvalidProviderOutput("Unexpected Anthropic response shape") from None
