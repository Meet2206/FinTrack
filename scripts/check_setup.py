"""Are keys, sheets and folders all OK?  Same as: python cli.py check"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finance.setup_check import run_checks  # noqa: E402

failed = 0
for c in run_checks():
    print(f"✅ {c.label}" if c.ok else f"❌ {c.label} → {c.fix}")
    failed += not c.ok
sys.exit(1 if failed else 0)
