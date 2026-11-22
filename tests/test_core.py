"""Unit tests: math check, fingerprints, keyword rules, settings, PDF tools, extraction helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finance import extract, pdf_tools
from finance.categorize import keyword_category
from finance.config import ConfigError, load_settings
from finance.demo import build_statement, write_pdf
from finance.extract import StatementChunk, Txn
from finance.ids import merchant_key, transaction_ids
from finance.reconcile import check


def row(date, debit=None, credit=None, balance=None, description="test"):
    return Txn(date=date, description=description, debit=debit, credit=credit, balance=balance)


# ── Reconciliation ───────────────────────────────────────────────────────────


def test_balanced_statement_passes():
    rows = [row("2026-11-01", debit=50, balance=950), row("2026-11-02", credit=100, balance=1050)]
    assert check(1000, 1050, rows) == []


def test_wrong_row_is_pinpointed_and_later_rows_are_not_flagged():
    rows = [
        row("2026-11-01", debit=50, balance=950),
        row("2026-11-02", debit=10, balance=900),
        row("2026-11-03", debit=100, balance=800),
    ]
    issues = check(1000, 800, rows)
    assert len(issues) == 1 and issues[0].startswith("Row 2")


def test_credit_card_balance_goes_up_with_spending():
    assert check(100, 140, [row("2026-11-01", debit=40, balance=140)], is_card=True) == []


def test_opening_balance_is_worked_out_from_first_row():
    assert check(None, 900, [row("2026-11-01", debit=100, balance=900)]) == []


def test_no_balances_at_all_cannot_be_verified():
    assert "can't be verified" in check(None, None, [row("2026-11-01", debit=5)])[0]


def test_closing_balance_mismatch_is_reported():
    assert "Closing balance" in check(1000, 999, [row("2026-11-01", debit=50)])[0]


def test_demo_statement_reconciles():
    stmt = build_statement("2026-11")
    assert check(stmt.opening_balance, stmt.closing_balance, stmt.transactions) == []


# ── Fingerprints ─────────────────────────────────────────────────────────────


def coffee(description="CAFE 12"):
    return Txn(date="2026-11-01", description=description, debit=3.5, credit=None, balance=None)


def test_identical_coffees_get_different_ids():
    a, b = transaction_ids("bank:1234", [coffee(), coffee()])
    assert a != b


def test_same_rows_always_get_same_ids():
    assert transaction_ids("bank:1234", [coffee()]) == transaction_ids("bank:1234", [coffee()])


def test_spacing_and_punctuation_do_not_change_ids():
    assert transaction_ids("bank:1", [coffee("CAFE  12")]) == transaction_ids("bank:1", [coffee("CAFE*12")])


def test_different_accounts_get_different_ids():
    assert transaction_ids("bank:1111", [coffee()]) != transaction_ids("bank:2222", [coffee()])


def test_merchant_key_ignores_reference_codes():
    assert merchant_key("AMZN Mktp US*2K4L95 Seattle") == merchant_key("AMZN Mktp US*9QX71 Seattle")
    assert merchant_key("AMZN Mktp US*2K4L95 Seattle") == "amzn mktp us"


# ── Keyword rules ────────────────────────────────────────────────────────────


def test_keywords_match_whole_words_only():
    keywords = {"Investments": ["sip"]}
    assert keyword_category("MUTUAL FUND SIP 2231", keywords) == "Investments"
    assert keyword_category("GOSSIP MAGAZINE", keywords) is None


def test_first_matching_category_wins():
    keywords = {"Subscriptions": ["gym"], "Travel": ["gym"]}
    assert keyword_category("CITY GYM", keywords) == "Subscriptions"


# ── Settings ─────────────────────────────────────────────────────────────────


def test_missing_config_gives_a_helpful_error(tmp_path):
    with pytest.raises(ConfigError, match="cp config.example.yaml"):
        load_settings(tmp_path / "nope.yaml")


def test_config_paths_are_relative_to_the_config_file_and_empty_sheets_dropped(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text('sheets:\n  Grocery: "abc"\n  Travel: ""\ndb_path: data/x.db\n')
    s = load_settings(cfg)
    assert s.sheets == {"Grocery": "abc"}
    assert s.db_path == tmp_path / "data" / "x.db"


def test_bad_setting_is_explained(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("pages_per_chunk: three\n")
    with pytest.raises(ConfigError, match="problem"):
        load_settings(cfg)


# ── PDF tools ────────────────────────────────────────────────────────────────


def test_locked_pdf_opens_only_with_the_right_password(tmp_path):
    path = write_pdf(build_statement("2026-11"), tmp_path / "s.pdf", "X-1", password="secret123")
    with pytest.raises(pdf_tools.WrongPassword):
        pdf_tools.open_pdf(path)
    with pytest.raises(pdf_tools.WrongPassword):
        pdf_tools.open_pdf(path, "wrong")
    assert len(pdf_tools.open_pdf(path, "secret123").pages) >= 1


def test_saved_password_is_tried_automatically(tmp_path):
    path = write_pdf(build_statement("2026-11"), tmp_path / "s.pdf", "X-1", password="secret123")
    pdf_tools.save_password("mainbank", "secret123")
    assert pdf_tools.saved_password_names() == ["mainbank"]
    assert pdf_tools.open_pdf(path) is not None


def test_not_a_pdf_is_rejected(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_text("hello")
    with pytest.raises(pdf_tools.BadPdf):
        pdf_tools.open_pdf(path)


def test_pages_are_split_into_groups(tmp_path):
    stmt = build_statement("2026-11")
    reader = pdf_tools.open_pdf(write_pdf(stmt, tmp_path / "s.pdf", "X-1", rows_per_page=5))
    groups = pdf_tools.page_groups(reader, 3)
    assert [len(g) for g in groups][:-1] == [3] * (len(groups) - 1)
    assert sum(len(g) for g in groups) == len(reader.pages)
    assert pdf_tools.pages_as_pdf(reader, groups[0]).startswith("JVBER")  # base64 of "%PDF"


# ── Extraction helpers (no API calls) ────────────────────────────────────────


def chunk(**kw) -> StatementChunk:
    base = dict(
        looks_like_statement=True,
        kind=None,
        bank_name=None,
        account_last4=None,
        currency=None,
        period_start=None,
        period_end=None,
        opening_balance=None,
        closing_balance=None,
        transactions=[],
    )
    return StatementChunk(**{**base, **kw})


def test_merge_takes_header_from_first_and_closing_from_last():
    a = chunk(bank_name="BANK", opening_balance=100, transactions=[row("2026-11-01", debit=1)])
    b = chunk(closing_balance=50, transactions=[row("2026-11-02", debit=2)])
    merged = extract.merge([a, b])
    assert (merged.bank_name, merged.opening_balance, merged.closing_balance) == ("BANK", 100, 50)
    assert [t.date for t in merged.transactions] == ["2026-11-01", "2026-11-02"]


def test_cut_off_answer_raises_chunk_too_long(monkeypatch):
    fake_resp = SimpleNamespace(
        stop_reason="max_tokens",
        parsed_output=None,
        usage=SimpleNamespace(input_tokens=10, output_tokens=16000),
    )
    fake_client = SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: fake_resp))
    monkeypatch.setattr(extract, "get_client", lambda: fake_client)
    calls = []
    with pytest.raises(extract.ChunkTooLong):
        extract.extract_pages("JVBER", "model", calls.append)
    assert calls and calls[0].output_tokens == 16000  # the cost is still logged


def test_refusal_raises_ai_declined(monkeypatch):
    fake_resp = SimpleNamespace(
        stop_reason="refusal", parsed_output=None, usage=SimpleNamespace(input_tokens=1, output_tokens=1)
    )
    monkeypatch.setattr(
        extract, "get_client", lambda: SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: fake_resp))
    )
    with pytest.raises(extract.AIDeclined):
        extract.extract_pages("JVBER", "model", lambda c: None)


def test_long_page_groups_are_split_in_half_and_retried(monkeypatch, tmp_path):
    reader = pdf_tools.open_pdf(
        write_pdf(build_statement("2026-11"), tmp_path / "s.pdf", "X", rows_per_page=4)
    )
    sizes = []

    def fake_extract_pages(pdf_b64, model, on_call):
        pages = len(
            pdf_tools.PdfReader(__import__("io").BytesIO(__import__("base64").b64decode(pdf_b64))).pages
        )
        sizes.append(pages)
        if pages > 1:
            raise extract.ChunkTooLong()
        return chunk(transactions=[row("2026-11-01", debit=1)])

    monkeypatch.setattr(extract, "extract_pages", fake_extract_pages)
    result = extract._extract_with_retry(reader, range(0, 3), "model", lambda c: None)
    assert len(result) == 3 and 1 in sizes and 3 in sizes


def test_missing_api_key_gives_a_clear_message(monkeypatch, settings, db, tmp_path):
    from finance import pipeline

    def no_credentials(**kwargs):
        raise TypeError('"Could not resolve authentication method. Expected one of api_key…"')

    monkeypatch.setattr(
        extract, "get_client", lambda: SimpleNamespace(messages=SimpleNamespace(parse=no_credentials))
    )
    path = write_pdf(build_statement("2026-11"), tmp_path / "s.pdf", "X-1")
    result = pipeline.process_statement(path, settings, db)
    assert result.status == "failed" and "No Claude API key" in result.message
