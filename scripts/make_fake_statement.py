"""Create a realistic FAKE bank statement PDF for trying the app safely.

python scripts/make_fake_statement.py                       # → data/inbox/fake_statement.pdf
python scripts/make_fake_statement.py --month 2026-10 --password secret123
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finance.demo import build_statement, write_pdf  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--month", default="2026-11", help="YYYY-MM (default 2026-11)")
parser.add_argument("--password", help="Lock the PDF with this password")
parser.add_argument("--out", default="data/inbox/fake_statement.pdf")
args = parser.parse_args()

stmt = build_statement(args.month)
path = write_pdf(stmt, Path(args.out), statement_no=f"FAKE-{args.month}", password=args.password)
print(f"Created {path} ({len(stmt.transactions)} transactions, closing balance {stmt.closing_balance:,.2f})")
print(f"Try it:  python cli.py process {path} --dry-run")
