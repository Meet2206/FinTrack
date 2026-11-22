"""Build a demo with NO API keys: 3 months of fake statements, read by a pretend Claude.

    python scripts/demo.py
    WDMMG_CONFIG=demo/config.yaml streamlit run app.py --server.address localhost

Everything lives in demo/ (delete it anytime). Google Sheets sync is not configured in the demo.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from finance import ledger, pipeline  # noqa: E402
from finance.config import load_settings  # noqa: E402
from finance.demo import build_statement, fake_claude, write_pdf  # noqa: E402

demo = ROOT / "demo"
if demo.exists():
    shutil.rmtree(demo)
demo.mkdir()
config = yaml.safe_load((ROOT / "config.example.yaml").read_text())
config["sheets"] = {}
config["pricing_per_million_tokens"] = {}
(demo / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
(demo / ".gitignore").write_text(".env\nservice_account.json\ndata/\n")

settings = load_settings(demo / "config.yaml")
db = ledger.connect(settings.db_path)
truths, files = {}, []
opening = 2500.00
for month in ("2026-09", "2026-10", "2026-11"):
    stmt = build_statement(month, opening=opening)
    number = f"DEMO-{month}"
    truths[number] = stmt
    files.append(write_pdf(stmt, demo / f"statement_{month}.pdf", statement_no=number))
    opening = stmt.closing_balance

with fake_claude(truths):
    for path in files:
        result = pipeline.process_statement(path, settings, db)
        print(f"{path.name}: {result.message}")

print("\nDemo ready. Start the app with:")
print("  WDMMG_CONFIG=demo/config.yaml streamlit run app.py --server.address localhost")
