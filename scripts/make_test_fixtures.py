"""Write the test-scenario PDFs into tests/fixtures/ so you can open them, upload them in the
app, or run them through the real Claude (python -m pytest -m live).

    python scripts/make_test_fixtures.py

Every file is FAKE data. tests/fixtures/README.md lists what each one is and what should happen.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.scenarios import SCENARIOS, write_scenario_file  # noqa: E402

FOLDER = ROOT / "tests" / "fixtures"
FOLDER.mkdir(parents=True, exist_ok=True)
for old in FOLDER.glob("*.pdf"):
    old.unlink()

STATUS = {
    "ready": "✅ ready",
    "synced": "✅ ready (nothing to sync)",
    "mismatch": "🔴 held for review",
    "failed": "🔴 rejected",
}
lines = [
    "# Test fixture files",
    "",
    "Fake statement PDFs, one per real-life situation. **All data is made up.**",
    "Regenerate with `python scripts/make_test_fixtures.py`. They're used by `tests/test_live.py`",
    "(the real Claude, opt-in) and you can upload them in the app to see each situation yourself.",
    "",
    "| File | Situation | What the app must do | Expected result | Password |",
    "|---|---|---|---|---|",
]
made = 0
for s in SCENARIOS:
    if "fixture" not in s.tags and not s.password:
        continue
    if s.reader not in ("text",) or s.max_rows_per_answer:
        continue  # situations about how the AI behaves can't be captured in a file
    path = write_scenario_file(s, FOLDER)
    made += 1
    lines.append(f"| `{path.name}` | {s.title} | {s.expect} | {STATUS[s.status]} | {s.password or '–'} |")

(FOLDER / "README.md").write_text("\n".join(lines) + "\n")
print(f"Wrote {made} fixture PDFs + README.md to {FOLDER}")
