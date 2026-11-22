"""Fingerprints for transactions and shop names.

In plain English:
- Transaction ID: built from account, date, amounts and description. The same
  transaction always gets the same ID, so overlapping statements can't create
  duplicates. A counter keeps two identical coffees on one day as two rows.
- Merchant key: a simplified shop name used to look up saved rules.
  "AMZN Mktp US*2K4L95 Seattle WA" → "amzn mktp us"
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter


def account_ref(kind: str | None, last4: str | None) -> str:
    """'bank:1234'. Used inside transaction IDs and to identify accounts."""
    return f"{kind or 'bank'}:{last4 or 'unknown'}"


def transaction_ids(account: str, txns) -> list[str]:
    seen: Counter[str] = Counter()
    ids = []
    for t in txns:
        description = re.sub(r"[^a-z0-9]", "", t.description.lower())  # ignore spacing/punctuation
        base = f"{account}|{t.date}|{t.debit}|{t.credit}|{description}"
        seen[base] += 1  # 1st identical coffee → |1, 2nd → |2
        ids.append(hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()[:16])
    return ids


def merchant_key(description: str) -> str:
    """'AMZN Mktp US*2K4L95 Seattle WA' → 'amzn mktp us' (letters only, first 3 words)."""
    words = re.sub(r"[^a-z ]", " ", description.lower()).split()
    return " ".join(words[:3])


def pretty_merchant(description: str) -> str:
    """A readable fallback shop name when nobody has named it yet."""
    words = [w for w in merchant_key(description).split() if len(w) > 1]  # "spotify p c" → "spotify"
    return " ".join(words).title() or description.strip()[:40]
