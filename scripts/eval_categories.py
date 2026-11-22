"""Measure categorization accuracy against transactions YOU labeled (uses the real Claude API).

    python scripts/eval_categories.py tests/data/labeled.csv

CSV columns: description,amount,expected   (amount: + money out, − money in)
Start from tests/data/labeled.example.csv. Keep your real labeled.csv private (it's gitignored).
"""

import csv
import sys
from collections import Counter
from itertools import batched
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finance import costs  # noqa: E402
from finance.categorize import ask_claude  # noqa: E402
from finance.config import load_settings  # noqa: E402

path = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/data/labeled.csv")
settings = load_settings()
rows = [
    {"txn_date": "", "description": r["description"], "amount": float(r["amount"]), "expected": r["expected"]}
    for r in csv.DictReader(path.open())
]
if not rows:
    sys.exit(f"No rows in {path}")

spent = []
correct, mixups = 0, Counter()
for batch in batched(rows, settings.categorize_batch_size):
    batch = list(batch)
    labels = ask_claude(
        batch, [], settings.model, on_call=lambda c: spent.append(costs.cost_usd(c, settings))
    )
    for n, r in enumerate(batch, start=1):
        got = labels[n].category if n in labels else "(skipped)"
        if got == r["expected"]:
            correct += 1
        else:
            mixups[(r["expected"], got, r["description"])] += 1

score = correct / len(rows)
print(f"Accuracy: {correct}/{len(rows)} = {score:.1%}  {'✅' if score >= 0.95 else '❌'} (target ≥ 95%)")
if mixups:
    print("Mix-ups (expected → got):")
    for (expected, got, description), _count in mixups.most_common(15):
        print(f'  {expected} → {got}   e.g. "{description}"')
print(f"Cost of this run: ${sum(spent):.4f}")
