"""Rebuild everything from scratch with one command (no API key, no network):

    python run_pipeline.py            # full rebuild, about 3 minutes
    python run_pipeline.py --no-proofs

fixtures -> synthetic documents + dataset (real workflow) -> SQL analyses + dump
-> Power BI exports + PBIP -> tests -> proofs -> security scan -> manifest

Synthetic demonstration data. No real client, legal-case or confidential LexLau/Klavis data is included.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("Build test fixtures (synthetic)", ["tests/fixtures/build_fixtures.py"]),
    ("Generate documents + replay the workflow into SQLite", ["scripts/build_dataset.py"]),
    ("Run the SQL analyses + full dump", ["scripts/run_sql_analysis.py"]),
    ("Export the Power BI star schema", ["scripts/export_powerbi_data.py"]),
    ("Build the Power BI project (TMDL + report) and DAX docs", ["scripts/build_powerbi_project.py"]),
    ("Run unit / integration / e2e tests", ["scripts/run_tests.py"]),
    ("Create the portfolio proofs", ["scripts/make_proofs.py"]),
    ("Security scan", ["scripts/security_scan.py"]),
    ("Write MANIFEST.csv", ["scripts/build_manifest.py"]),
]

if "--no-proofs" in sys.argv:
    STEPS = [s for s in STEPS if "proofs" not in s[1][0]]

for i, (label, cmd) in enumerate(STEPS, 1):
    print(f"\n=== [{i}/{len(STEPS)}] {label}", flush=True)
    if subprocess.run([sys.executable, *cmd], cwd=ROOT).returncode != 0:
        sys.exit(f"Pipeline stopped at step {i}: {cmd[0]} failed")
print("\nPipeline completed. Start the demo with: python -m app.backend.server")
