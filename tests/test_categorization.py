"""Categorization: saved rules → keywords → AI, confidence and review, batching, the AI prompt."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finance import categorize, ledger, pipeline
from finance.categorize import Labeled, Labels, ask_claude
from finance.demo import build_statement, fake_ask_claude, fake_claude, write_pdf


@pytest.fixture
def run(settings, db, tmp_path):
    """Process a statement; record exactly which rows were sent to the (pretend) AI."""
    counter = iter(range(1, 100))
    sent: list[list[str]] = []

    def spy_ask_claude(batch, corrections, model, on_call):
        sent.append([r["description"] for r in batch])
        return fake_ask_claude(batch, corrections, model, on_call)

    def _run(rows, month="2026-11", ai=spy_ask_claude):
        stmt = build_statement(month, rows=rows)
        number = f"C-{next(counter)}"
        with fake_claude({number: stmt}):
            categorize.ask_claude = ai
            result = pipeline.process_statement(
                write_pdf(stmt, tmp_path / f"{number}.pdf", number), settings, db
            )
        return result

    _run.sent = sent
    return _run


def category_of(db, description):
    return db.execute(
        "SELECT category, category_source, confidence, needs_review FROM transactions WHERE description = ?",
        (description,),
    ).fetchone()


def test_keyword_rows_never_reach_the_ai(run, db):
    run(
        [
            (2, "SPOTIFY P2C3", 10.99, None),
            (3, "SHELL FUEL STATION 22", 40.0, None),
            (4, "POS 4471 FRSHMRT*CTY", 54.2, None),
        ]
    )
    assert run.sent == [["POS 4471 FRSHMRT*CTY"]]
    assert tuple(category_of(db, "SPOTIFY P2C3"))[:2] == ("Subscriptions", "keyword")


def test_known_shops_are_free_the_second_month(run, db):
    rows = [(2, "POS 4471 FRSHMRT*CTY", 54.2, None), (5, "GREEN GROCER CO", 20.0, None)]
    run(rows, month="2026-10")
    run(rows, month="2026-11")
    assert len(run.sent) == 1, "month 2 needed no AI call at all"
    rule_uses = db.execute("SELECT SUM(times_used) FROM merchant_rules").fetchone()[0]
    assert rule_uses == 2


def test_only_confident_ai_answers_become_rules(run, db):
    run([(2, "CLOUDBOX STORAGE", 9.99, None), (3, "POS 4471 FRSHMRT*CTY", 54.2, None)])
    keys = set(ledger.merchant_rules(db))
    assert "pos frshmrt cty" in keys and "cloudbox storage" not in keys  # CloudBox was only 'medium'


def test_your_correction_wins_over_the_ai_next_month(run, db):
    run([(2, "PIZZA PALACE DELIVERY", 27.5, None)], month="2026-10")
    fixed = ledger.transactions_frame(db)
    edited = fixed.copy()
    edited["category"] = "Grocery"  # you decide pizza delivery counts as groceries
    ledger.apply_user_edits(db, fixed, edited, remember=True)
    run([(3, "PIZZA PALACE DELIVERY", 31.0, None)], month="2026-11")
    row = db.execute(
        "SELECT category, category_source FROM transactions WHERE txn_date = '2026-11-03'"
    ).fetchone()
    assert tuple(row) == ("Grocery", "rule")


def test_ai_rule_never_overwrites_your_rule(db):
    ledger.save_rule(db, "pizza palace delivery", "Pizza Palace", "Grocery", "user")
    ledger.save_rule(db, "pizza palace delivery", "Pizza Palace", "Other", "ai")
    assert ledger.merchant_rules(db)["pizza palace delivery"][1] == "Grocery"
    ledger.save_rule(db, "pizza palace delivery", "Pizza Palace", "Other", "user")
    assert ledger.merchant_rules(db)["pizza palace delivery"][1] == "Other", "but you can change your mind"


@pytest.mark.parametrize(
    "review_if, expected_review",
    [
        (["low", "medium"], {"CLOUDBOX STORAGE", "MYSTERY SHOP 77"}),
        (["low"], {"MYSTERY SHOP 77"}),
        ([], set()),
        (["low", "medium", "high"], {"CLOUDBOX STORAGE", "MYSTERY SHOP 77", "POS 4471 FRSHMRT*CTY"}),
    ],
    ids=["default-low-and-medium", "only-low", "never", "everything-the-ai-decides"],
)
def test_review_threshold_is_configurable(run, db, settings, review_if, expected_review):
    settings.review.review_if_confidence = review_if
    run(
        [
            (2, "CLOUDBOX STORAGE", 9.99, None),
            (3, "MYSTERY SHOP 77", 12.0, None),
            (4, "POS 4471 FRSHMRT*CTY", 54.2, None),
            (5, "SPOTIFY P2C3", 10.99, None),
        ]
    )
    flagged = {r[0] for r in db.execute("SELECT description FROM transactions WHERE needs_review = 1")}
    assert flagged == expected_review, "keyword/rule matches are never sent to review"


def test_row_the_ai_skipped_goes_to_review_as_other(run, db):
    def skips_second_row(batch, corrections, model, on_call):
        labels = fake_ask_claude(batch, corrections, model, on_call)
        labels.pop(2)
        return labels

    run([(2, "POS 4471 FRSHMRT*CTY", 54.2, None), (3, "GREEN GROCER CO", 20.0, None)], ai=skips_second_row)
    row = category_of(db, "GREEN GROCER CO")
    assert (row["category"], row["confidence"], row["needs_review"]) == ("Other", "low", 1)


def test_unknown_shops_are_sent_in_batches_of_100(run, db, settings):
    rows = [
        (1 + i % 28, f"UNKNOWN SHOP {chr(65 + i // 26)}{chr(65 + i % 26)}", 5.0, None) for i in range(250)
    ]
    run(rows)
    assert [len(batch) for batch in run.sent] == [100, 100, 50]
    assert db.execute("SELECT COUNT(*) FROM transactions WHERE category IS NULL").fetchone()[0] == 0


def test_categorization_failure_is_safe_to_retry(run, db):
    def broken(batch, corrections, model, on_call):
        raise RuntimeError("Categorization stopped early: max_tokens")

    rows = [(2, "POS 4471 FRSHMRT*CTY", 54.2, None), (3, "MYSTERY SHOP 77", 12.0, None)]
    first = run(rows, ai=broken)
    assert first.status == "failed"
    assert db.execute("SELECT COUNT(*) FROM transactions WHERE category IS NULL").fetchone()[0] == 2
    second = run(rows)  # a freshly downloaded copy: a different file containing the same rows
    assert second.status in ("ready", "synced")
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2, "no duplicates after the retry"
    assert db.execute("SELECT COUNT(*) FROM transactions WHERE category IS NULL").fetchone()[0] == 0


# ── What exactly is sent to Claude ───────────────────────────────────────────


def fake_parse(captured: dict, labels: list[Labeled], stop_reason="end_turn"):
    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            stop_reason=stop_reason,
            parsed_output=Labels(items=labels),
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )

    return parse


def test_ai_request_contains_rows_rules_and_your_corrections(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        categorize,
        "claude_parse",
        fake_parse(captured, [Labeled(n=1, merchant="Fresh Mart", category="Grocery", confidence="high")]),
    )
    calls = []
    labels = ask_claude(
        [{"txn_date": "2026-11-02", "amount": 54.2, "description": "POS 4471 FRSHMRT*CTY"}],
        ['"PIZZA PALACE DELIVERY" → Grocery'],
        "claude-opus-5-5",
        calls.append,
    )
    assert labels[1].category == "Grocery"
    assert captured["model"] == "claude-opus-5-5" and captured["output_format"] is Labels
    assert "1 | 2026-11-02 | 54.20 | POS 4471 FRSHMRT*CTY" in captured["messages"][0]["content"]
    assert (
        "Not an expense" in captured["system"] and '"PIZZA PALACE DELIVERY" → Grocery' in captured["system"]
    )
    assert calls[0].purpose == "categorize" and calls[0].input_tokens == 100


def test_cut_off_categorization_answer_raises(monkeypatch):
    monkeypatch.setattr(categorize, "claude_parse", fake_parse({}, [], stop_reason="max_tokens"))
    with pytest.raises(RuntimeError, match="max_tokens"):
        ask_claude([{"txn_date": "2026-11-02", "amount": 1.0, "description": "X"}], [], "m", lambda c: None)
