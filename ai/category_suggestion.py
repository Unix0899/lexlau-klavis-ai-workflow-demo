"""Category suggestion over a simple fictional taxonomy.

The suggestion is only a proposal: the reviewer can always change the category
before the case is created (and later, from the case page).
"""
import re

from . import bug_replay

TAXONOMY = {
    "Commercial dispute": [
        "invoice", "invoices", "unpaid", "delivery", "delivered", "supplier", "goods",
        "purchase order", "packaging", "late payment", "payment reminder", "customer",
    ],
    "Contract dispute": [
        "breach of contract", "service agreement", "termination clause", "contractual",
        "non-performance", "penalty clause", "contract", "clause",
    ],
    "Employment matter": [
        "employee", "employer", "dismissal", "notice period", "overtime", "salary",
        "labour", "workplace",
    ],
    "Corporate matter": [
        "shareholder", "shareholders", "board", "articles of association", "general meeting",
        "capital increase", "director", "share transfer",
    ],
    "Administrative matter": [
        "permit", "municipality", "administrative decision", "fine", "zoning",
        "public authority", "licence",
    ],
}


def _count(keyword, text_lower):
    if bug_replay.is_on("category_substring"):
        # BUG-02 replay: plain substring search, so 'board' is found inside 'cardboard'
        return text_lower.count(keyword)
    return len(re.findall(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])", text_lower))


def score_categories(text: str) -> dict:
    t = text.lower()
    scores = {}
    for category, keywords in TAXONOMY.items():
        s = 0
        for kw in keywords:
            n = _count(kw, t)
            s += n * (2 if " " in kw else 1)  # phrases are stronger evidence than single words
        scores[category] = s
    return scores


def suggest_category(text: str) -> dict:
    scores = score_categories(text)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top, top_score = ranked[0]
    total = sum(scores.values())
    if top_score == 0:
        return {"category": "Other", "confidence": 0.40, "scores": scores}
    share = top_score / total
    confidence = round(min(0.95, 0.45 + 0.5 * share), 2)
    return {"category": top, "confidence": confidence, "scores": scores}
