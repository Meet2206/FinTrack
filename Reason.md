# FinTrack design rationale

## Why local-first processing

Bank statements contain sensitive financial information. Local parsing keeps
the PDF, ledger, categorization, alerts, and suggestions on the user's device,
avoids recurring API costs, and makes test results repeatable.

## Why reconciliation is mandatory

A parser can misunderstand a date, sign, or amount. Replaying every row from
the opening balance and comparing it with the printed closing balance catches
those errors before they reach the Sheet. A mismatch is held for review.

## Why rules are preferred for categorization

Saved merchant rules and keywords are fast, predictable, and easy to audit.
When a user corrects a category, the correction becomes a rule for future
statements. Uncertain matches stay visible instead of being silently guessed.

## Why suggestions are deliberately conservative

The app can point out patterns—recurring subscriptions, repeated merchants,
and a category that dominates spending—but it cannot know the user's goals or
obligations. Suggestions therefore show the evidence and a modest estimate;
they never transfer money or make a financial decision.

## Why Google Sheets is a mirror

SQLite is the local source of truth because it supports deduplication, review,
alerts, and safe retries. Google Sheets is a convenient human-readable mirror.
Rebuilding affected month tabs makes sync idempotent and recoverable.

## Why this qualifies as useful automation

The workflow automates repetitive, checkable work—reading rows, checking
arithmetic, grouping categories, finding recurring charges, and updating
monthly tabs—while leaving judgment and approval with the user. That is the
right boundary for personal finance automation.
