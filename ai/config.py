"""Central settings for the demo.

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.

Every value can be overridden with an environment variable (see .env.example).
No secret is ever stored here: external provider keys are only read from the
environment, and the demo runs without any key (MockAIProvider is the default).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DISCLOSURE = ("Synthetic demonstration data. "
              "No real client, legal-case or confidential LexLau/Klavis data is included.")
AI_DRAFT_NOTICE = "AI-generated draft for demonstration purposes. Human validation required."
ASSISTANT_NOTICE = "Demo assistant — not legal advice."

# Upload rules (TEST 011 / TEST 012)
MAX_UPLOAD_BYTES = int(os.environ.get("LEXLAU_MAX_UPLOAD_BYTES", 5 * 1024 * 1024))
ALLOWED_FORMATS = ("pdf", "docx", "png", "jpg")

# A run whose overall confidence is below this threshold needs a closer human review
REVIEW_CONFIDENCE_THRESHOLD = float(os.environ.get("LEXLAU_REVIEW_THRESHOLD", 0.80))

# Provider chain. "mock" needs no key; "openai" / "anthropic" are optional.
PRIMARY_PROVIDER = os.environ.get("LEXLAU_PRIMARY_PROVIDER", "mock")
FALLBACK_PROVIDER = os.environ.get("LEXLAU_FALLBACK_PROVIDER", "mock-fallback")
PROVIDER_TIMEOUT_S = float(os.environ.get("LEXLAU_PROVIDER_TIMEOUT_S", 20))

DATABASE_PATH = Path(os.environ.get("LEXLAU_DATABASE", ROOT / "database" / "app_runtime.sqlite"))
REFERENCE_DATABASE = ROOT / "database" / "klavis_ai_demo.sqlite"
LOG_PATH = Path(os.environ.get("LEXLAU_LOG_PATH", ROOT / "logs" / "app.log"))

# The fields scored against ground truth (see docs/AI_QUALITY_FRAMEWORK.md)
SCORED_FIELDS = (
    "case_title", "case_reference", "client_name", "opposing_party", "document_type",
    "jurisdiction", "important_dates", "amounts", "case_category",
)
# Fields a case cannot be complete without
REQUIRED_FIELDS = (
    "case_reference", "client_name", "opposing_party", "jurisdiction",
    "important_dates", "amounts", "case_category",
)

CATEGORIES = (
    "Commercial dispute", "Contract dispute", "Employment matter",
    "Corporate matter", "Administrative matter", "Other",
)
