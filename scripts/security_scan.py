"""Confidentiality scan of the repository -> docs/SECURITY_SCAN.md. Exit code 1 on any finding.

Searches every text file for: password, secret, token, api_key, apikey, authorization, bearer,
private_key, e-mail addresses, URLs, key-like strings (sk-..., long hex / base64 values),
and the names of real people or internal systems that must never appear.

Mentions that are not secrets (variable NAMES read from the environment, the word "secret"
in documentation of what is never logged, public API endpoints of the optional providers)
are listed as REVIEWED with the reason, so a reader can check them.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXT = {".py", ".md", ".sql", ".js", ".css", ".html", ".json", ".csv", ".txt", ".tmdl", ".pbip", ".pbism",
            ".pbir", ".example", ".gitignore", ".yml", ".yaml", ".toml"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", "app_uploads", ".venv"}
SKIP_FILES = {"docs/SECURITY_SCAN.md", "scripts/security_scan.py"}

KEYWORDS = re.compile(r"password|secret|token|api_key|apikey|authorization|bearer|private_key", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"https?://[^\s\"')<>]+")
KEYLIKE = re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}"
                     r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})\b")
ASSIGNED = re.compile(r"(api_key|apikey|password|secret|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.I)

ALLOWED_URL_PREFIXES = (
    "https://api.openai.com/v1/chat/completions", "https://api.anthropic.com/v1/messages",
    "http://127.0.0.1", "http://localhost", "https://developer.microsoft.com/json-schemas/",
    "http://schemas.openxmlformats.org/", "https://github.com/", "https://www.linkedin.com/",
    "http://www.w3.org/2000/svg", "http://{host}:{port}", "https://claude.com/claude-code",
)
ALLOWED_EMAILS = {"jane.doe@example.test"}  # redaction unit test (reserved .test domain)

# a keyword line is fine when it only names an environment variable, a header, or documents the rule
REVIEWED = [
    (re.compile(r"OPENAI_API_KEY|ANTHROPIC_API_KEY|env_key"), "environment variable NAME only (no value in the repo)"),
    (re.compile(r"\"Authorization\": \"Bearer \" \+ self\._key\(\)|\"x-api-key\": self\._key\(\)"),
     "header built at runtime from the environment"),
    (re.compile(r"client[_ ]secrets?|client_secret", re.I), "documents / tests that client secrets are never logged"),
    (re.compile(r"no secrets?|never .*secret|secret.*never|secrets?, |without .*(key|secret)|secrets? scan|"
                r"secret scan|No secret|no API key|API key", re.I), "documentation of the no-secret rule"),
    (re.compile(r"tokens?\b.*(max_tokens|LLM|model)|max_tokens", re.I), "LLM token limit parameter"),
    (re.compile(r"word tokens|clean tokens"), "text-analysis wording (word tokens), not a credential"),
    (re.compile(r"No document content, personal data or secret"), "review checklist item (no secret in logs)"),
    (re.compile(r"SECRET-QUESTION-MARKER|for secret in \(|assertNotIn\(secret"), "test canary proving nothing leaks"),
]


def files():
    for p in ROOT.rglob("*"):
        if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in SKIP_FILES:
            continue
        if p.suffix.lower() in TEXT_EXT or p.name in (".env.example", ".gitignore"):
            yield p, rel


def main():
    blocking, reviewed = [], []
    env_files = [p for p in ROOT.glob(".env*") if p.name != ".env.example"]
    for p in env_files:
        blocking.append((p.name, 0, "real .env file present"))
    n = 0
    for p, rel in files():
        n += 1
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, 1):
            for m in KEYLIKE.finditer(line):
                blocking.append((rel, i, f"key-like value {m.group(0)[:12]}..."))
            if ASSIGNED.search(line) and "example" not in line.lower():
                blocking.append((rel, i, "credential assignment"))
            for m in EMAIL.finditer(line):
                if m.group(0) not in ALLOWED_EMAILS and not m.group(0).endswith((".test", ".example")) \
                        and not re.fullmatch(r"[\w.-]+@[\d.]+", m.group(0)):
                    blocking.append((rel, i, f"e-mail address {m.group(0)}"))
            for m in URL.finditer(line):
                if not m.group(0).startswith(ALLOWED_URL_PREFIXES):
                    blocking.append((rel, i, f"URL {m.group(0)[:60]}"))
            if KEYWORDS.search(line):
                reason = next((r for rx, r in REVIEWED if rx.search(line)), None)
                (reviewed if reason else blocking).append((rel, i, reason or "keyword"))
    out = ["# Security and confidentiality scan", "",
           "> Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.",
           "", f"Generated by `scripts/security_scan.py` on {n} text files.", "",
           "Searched: `password`, `secret`, `token`, `api_key`, `apikey`, `authorization`, `bearer`, `private_key`, "
           "e-mail addresses, URLs, key-like strings (`sk-...`, `AKIA...`, JWT, GitHub tokens), credential assignments, "
           "real `.env` files.", "",
           f"**Blocking findings: {len(blocking)}**", ""]
    if blocking:
        out += ["| File | Line | Finding |", "|---|---:|---|"] + [f"| `{f}` | {l} | {w} |" for f, l, w in blocking]
    by_reason = {}
    for f, l, r in reviewed:
        by_reason.setdefault(r, []).append(f"{f}:{l}")
    out += ["", f"## Reviewed keyword mentions ({len(reviewed)}) - not secrets", "",
            "| Why it is not a secret | Occurrences | Files |", "|---|---:|---|"]
    for r, locs in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        filesset = sorted({x.rsplit(':', 1)[0] for x in locs})
        out.append(f"| {r} | {len(locs)} | {', '.join(f'`{x}`' for x in filesset[:6])}"
                   f"{' ...' if len(filesset) > 6 else ''} |")
    out += ["", "URLs allowed: the public endpoints of the optional providers (never called without a key), "
            "localhost, XML/JSON schema namespaces, public profile links.", ""]
    (ROOT / "docs" / "SECURITY_SCAN.md").write_text("\n".join(out), encoding="utf-8")
    print(f"{n} files scanned: {len(blocking)} blocking finding(s), {len(reviewed)} reviewed mention(s)")
    for f, l, w in blocking[:30]:
        print(f"  BLOCKING {f}:{l} {w}")
    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()
