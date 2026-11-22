"""Check every link between the project's Markdown docs.

In plain English: opens every .md file, finds each link to another file or to a
heading (#section), and reports any that point nowhere. Web links are skipped.

    python scripts/check_doc_links.py      # exits with 1 if anything is broken
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".venv", "demo", "data", ".pytest_cache", ".ruff_cache", ".git", "node_modules"}
CODE = re.compile(r"```.*?```", re.DOTALL)
HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
LINK = re.compile(r"\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    """The #anchor GitHub gives a heading: lowercase, punctuation dropped, spaces → dashes."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def docs() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if not SKIP & set(p.relative_to(ROOT).parts))


def main() -> int:
    files = docs()
    anchors = {p: {slug(h) for h in HEADING.findall(CODE.sub("", p.read_text()))} for p in files}
    broken = []
    for doc in files:
        for link in LINK.findall(CODE.sub("", doc.read_text())):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            target, _, anchor = link.partition("#")
            path = (doc.parent / target).resolve() if target else doc
            if not path.exists():
                broken.append(f"{doc.relative_to(ROOT)}: missing file → {link}")
            elif anchor and path.suffix == ".md" and anchor not in anchors.get(path, set()):
                broken.append(f"{doc.relative_to(ROOT)}: missing heading → {link}")
    print("\n".join(broken))
    print(f"Checked {len(files)} docs: {len(broken)} broken links")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
