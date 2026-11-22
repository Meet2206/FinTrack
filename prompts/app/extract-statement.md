# 📄 Prompt: read a statement

[← Prompts folder](../README.md) · **Read a statement** · [Sort into categories](categorize-transactions.md)

| | |
|---|---|
| **Status** | 🟢 **Live.** The app reads this file every time it starts. Editing the text between the markers changes what Claude is told. |
| **Used by** | `finance/extract.py` → `EXTRACT_PROMPT` |
| **Sent** | Once per group of 3 PDF pages, as the *system prompt* (the standing instructions Claude follows for that request) |
| **Claude's job** | Copy every transaction off the pages into a strict form. **Copy only, no math.** The app does all the math and checks Claude's copying against the statement's own balances. |

---

## The prompt

Only the text between the two markers is sent. Everything else in this file is notes for people.

<!-- prompt:start -->
```text
You read bank and credit card statement pages and copy out the transactions.

Rules:
- List every transaction row on these pages, in the order printed.
- Skip rows that are not transactions: 'balance brought forward', 'carried forward',
  page totals, subtotals and repeated table headers.
- Copy amounts exactly as printed. Never calculate, round or guess a number.
- Write dates as YYYY-MM-DD. Use the statement period to work out the year, and
  whether dates are printed day-first or month-first.
- If a description wraps onto several lines, join it into one line.
- For the account or card number, return only the last 4 digits.
- Use null for anything not shown on these pages.
```
<!-- prompt:end -->

---

## What else Claude receives with it

> 💡 The prompt above says *how* to work. These parts say *what* to work on and *what shape* the answer must have. They're fixed in the code, because the code depends on their exact shape.

**1. The pages:** up to 3 pages of the statement, sent as a small PDF (Claude sees the layout, tables and text exactly as you would).

**2. A one-line request:**

```text
Copy out the transactions on these pages.
```

**3. The form Claude must fill in** (from `finance/extract.py`). Claude can't answer in free text: the answer must fit this form, and the app rejects anything that doesn't.

| Field | What Claude is told about it |
|---|---|
| `looks_like_statement` | False if these pages are not from a bank or credit card statement |
| `kind` | `bank` or `card` ("card" for a credit card statement) |
| `bank_name` | (no extra description) |
| `account_last4` | Last 4 digits of the account/card number only |
| `currency` | ISO 4217 code, e.g. USD, EUR, INR |
| `period_start`, `period_end` | YYYY-MM-DD |
| `opening_balance`, `closing_balance` | Only if printed on these pages |
| `transactions` | A list of rows, each with the fields below |
| ↳ `date` | Transaction date as YYYY-MM-DD |
| ↳ `description` | Exactly as printed; join the lines if it wraps |
| ↳ `debit` | Money out (or a charge on a credit card), as a positive number |
| ↳ `credit` | Money in (or a payment/refund on a credit card), as a positive number |
| ↳ `balance` | Running balance printed after this row, if any |

---

## Why each rule is there

| Rule | Why | What goes wrong without it |
|---|---|---|
| "Every transaction row… in the order printed" | The math check replays the rows in order against the running balance. | Reordered rows make correct numbers look wrong. |
| "Skip 'balance brought forward'… page totals…" | These lines look like rows but aren't money moving. | A "carried forward 1,240.00" counted as a purchase. The math check would catch it, but it's better not to make the mistake. |
| "Copy amounts exactly… Never calculate, round or guess" | The app checks Claude's copying against the bank's own balances. That check only means something if Claude copied rather than computed. | A guessed number that happens to look plausible. |
| "Dates as YYYY-MM-DD… use the statement period" | Statements print "03/11" or "11 Mar" with no year. The period (e.g. Dec 2026 to Jan 2027) settles the year and whether 03/11 is 3 Nov or 11 Mar. | A January row filed under last year. The app's date check catches dates outside the period, but this prevents them. |
| "Join wrapped descriptions" | Long shop names wrap onto two lines in narrow columns. | One purchase read as two rows, one with no amount. |
| "Only the last 4 digits" | Your full account number never needs to leave the page. | A full account number stored in the database and Google Sheets. |
| "Null for anything not shown" | Page 2 of a statement usually has no balances. "Not shown" must not become "0". | A made-up opening balance of 0 makes the whole statement fail the math check. |

The answer is **checked, not trusted**: the math check, the date check and the "is this even a statement?" check all run on it before anything is saved. See [Architecture](../../Architecture.md) and [how the tests prove the math check works](../../TESTING.md#7-how-tests-prove-the-math-check-works).

---

## Editing it safely

1. Change only the text **between** `<!-- prompt:start -->` and `<!-- prompt:end -->`. Keep the ` ```text ` fence lines.
2. Run the free tests: `python -m pytest`. They check this file still loads and that the key rules (like "Never calculate") are still in it.
3. Run the real-Claude tests, which read 18 fake statements and check every one to the cent (about $0.50): `python -m pytest -m live`
4. Restart the web app, since prompts are read once at startup.

If you break something: `git checkout -- prompts/app/extract-statement.md` puts it back.

**Good edits:** a rule for a layout your bank uses ("Some banks print debits in brackets, like (54.20). Treat those as debits."), or a row type to skip ("Skip 'Reward points' summary rows.").
**Edits to avoid:** asking Claude to total, convert or categorize anything. Math belongs in the code, where it's checked, and categorizing is the [other prompt's](categorize-transactions.md) job.
