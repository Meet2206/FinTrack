"""Load the AI's instructions from the Markdown files in prompts/app/.

In plain English: provider instructions live in normal documents you can
read and edit (prompts/app/*.md), not buried in Python code. Each file explains
the prompt for humans, and the exact text the provider receives sits between two
markers:

    <!-- prompt:start -->
    ```text
    ...the words the provider reads...
    ```
    <!-- prompt:end -->

Everything outside the markers is notes for people and is never sent.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "app"

# A marker counts only on a line of its own, so notes can mention the markers in passing.
_BLOCK = re.compile(
    r"^[ \t]*<!--\s*prompt:start\s*-->[ \t]*$(.*?)^[ \t]*<!--\s*prompt:end\s*-->[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_FENCE = re.compile(r"\A```[\w-]*\n(.*)\n```\Z", re.DOTALL)


class PromptFileError(Exception):
    """A prompt file is missing or its markers are broken."""


def parse(text: str, source: str = "prompt file") -> str:
    """Return the text between the prompt markers, without the ``` fence around it."""
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        found = "no" if not blocks else str(len(blocks))
        raise PromptFileError(
            f"{source} has {found} prompt blocks; it needs exactly one, between "
            "<!-- prompt:start --> and <!-- prompt:end -->, each on a line of its own."
        )
    body = blocks[0].strip()
    fenced = _FENCE.match(body)
    prompt = (fenced.group(1) if fenced else body).strip()
    if not prompt:
        raise PromptFileError(f"{source}: the prompt between the markers is empty.")
    return prompt


@cache
def load(name: str, folder: Path = PROMPTS_DIR) -> str:
    """Read prompts/app/<name>.md and return the exact text the provider receives."""
    path = folder / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PromptFileError(
            f"Prompt file {path} is missing. Restore it from git: git checkout -- prompts/app/{name}.md"
        ) from None
    return parse(text, source=str(path))
