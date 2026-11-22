"""Project-wide pytest setup: the plain-English test report.

    python -m pytest --report TESTING.md

writes every result, described in plain English, into TESTING.md between the
TEST-RESULTS markers. (It lives here, at the project root, so pytest always loads it
before reading the --report option.) Test fixtures live in tests/conftest.py.
"""

from __future__ import annotations

import pytest

# ── Plain-English test report: python -m pytest --report TESTING.md ───────────

REPORT_START = "<!-- TEST-RESULTS:START -->"
REPORT_END = "<!-- TEST-RESULTS:END -->"
AREAS = {
    "test_scenarios": "📄 Statement scenarios: reading and checking real-life statements",
    "test_core": "🧮 Building blocks: math check, fingerprints, settings, PDFs",
    "test_pipeline": "🔁 End-to-end: PDF → database → Google Sheets",
    "test_categorization": "🗂️ Categorization: rules, keywords, AI, review",
    "test_sheets_mirror": "📊 Google Sheets writer and database upgrades",
    "test_alerts": "🚨 Alerts: every rule on both sides of its threshold",
    "test_cli": "⌨️ Command line",
    "test_settings_and_automation": "⚙️ Settings, monthly summary, Telegram, automation, setup checklist",
    "test_app": "🖥️ Web app pages",
    "test_live": "🌐 Live: the real Claude (opt-in)",
}
_results: list[dict] = []


def pytest_addoption(parser):
    parser.addoption(
        "--report",
        default=None,
        metavar="FILE",
        help="Write plain-English results into FILE between the TEST-RESULTS markers",
    )


def _describe(item) -> str:
    params = getattr(item, "callspec", None)
    scenario = params.params.get("scenario") if params else None
    if scenario is not None:
        return f"**{scenario.id}**: {scenario.title} → *{scenario.expect}*"
    doc = (getattr(item.function, "__doc__", None) or "").strip().split("\n")[0]
    text = doc or item.originalname.removeprefix("test_").replace("_", " ").capitalize()
    return f"{text} (`{params.id}`)" if params else text


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" or (rep.when == "setup" and not rep.passed):
        _results.append(
            {
                "area": item.module.__name__.split(".")[-1],
                "what": _describe(item),
                "outcome": rep.outcome,
                "seconds": rep.duration,
                "test": item.nodeid,
            }
        )


def pytest_sessionfinish(session, exitstatus):
    target = session.config.getoption("--report")
    if not target or not _results:
        return
    import platform
    from datetime import datetime
    from pathlib import Path

    icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}
    totals = {k: sum(r["outcome"] == k for r in _results) for k in icon}
    lines = [
        REPORT_START,
        "",
        f"**Last run:** {datetime.now():%Y-%m-%d %H:%M} · **{totals['passed']} passed** · "
        f"{totals['failed']} failed · {totals['skipped']} skipped · "
        f"{sum(r['seconds'] for r in _results):.1f} s of test time · Python {platform.python_version()}",
        "",
    ]
    for area, title in AREAS.items():
        rows = [r for r in _results if r["area"] == area]
        if not rows:
            continue
        passed = sum(r["outcome"] == "passed" for r in rows)
        lines += [
            f"<details><summary><b>{title}</b>: {passed}/{len(rows)} passed</summary>",
            "",
            "| # | What is checked | Result |",
            "|---|---|---|",
        ]
        lines += [f"| {i} | {r['what']} | {icon[r['outcome']]} |" for i, r in enumerate(rows, start=1)]
        lines += ["", "</details>", ""]
    lines.append(REPORT_END)
    block = "\n".join(lines)

    path = Path(target)
    text = path.read_text() if path.exists() else ""
    if REPORT_START in text and REPORT_END in text:
        before, rest = text.split(REPORT_START, 1)
        text = before + block + rest.split(REPORT_END, 1)[1]
    else:
        text = text + "\n" + block + "\n"
    path.write_text(text)
