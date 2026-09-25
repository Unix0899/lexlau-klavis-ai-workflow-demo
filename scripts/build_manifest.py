"""Write MANIFEST.csv: every file of the repository with its size and role."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", "app_uploads", "logs"}
ROLES = [("data/synthetic_documents/", "synthetic document"), ("data/", "synthetic dataset"),
         ("database/", "SQLite database"), ("sql/", "SQL"), ("ai/", "AI layer"), ("app/backend/", "backend"),
         ("app/frontend/", "frontend"), ("tests/fixtures/", "test fixture"), ("tests/", "tests"),
         ("powerbi/", "Power BI"), ("proofs/", "proof"), ("docs/", "documentation"), ("scripts/", "pipeline script"),
         ("portfolio/", "portfolio asset")]


def main():
    rows = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if p.is_dir() or any(part in SKIP for part in p.parts) or rel == "database/app_runtime.sqlite":
            continue
        role = next((r for prefix, r in ROLES if rel.startswith(prefix)), "project file")
        rows.append((rel, p.stat().st_size, role))
    with open(ROOT / "MANIFEST.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "bytes", "role"])
        w.writerows(rows)
    print(f"MANIFEST.csv: {len(rows)} files")


if __name__ == "__main__":
    main()
