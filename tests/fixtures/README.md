# Test fixture files

Fake statement PDFs, one per real-life situation. **All data is made up.**
Regenerate with `python scripts/make_test_fixtures.py`. They're used by `tests/test_live.py`
(the real Claude, opt-in) and you can upload them in the app to see each situation yourself.

| File | Situation | What the app must do | Expected result | Password |
|---|---|---|---|---|
| `S01-standard.pdf` | A normal month: 2-page bank statement, 31 transactions | Read every row, balances match, everything categorized | ✅ ready | – |
| `S02-long-20-pages.pdf` | A very busy month: 320 transactions over 20 pages | Read in groups of 3 pages, stitched back together, nothing lost | ✅ ready | – |
| `S04-one-row.pdf` | A statement with a single transaction | Works the same as a big one | ✅ ready | – |
| `S05-quiet-month.pdf` | A quiet month: zero transactions, opening = closing | Accepted as a valid statement with 0 rows (nothing to sync, so it's already 'synced') | ✅ ready (nothing to sync) | – |
| `S06-credit-card.pdf` | A credit card statement (balance = what you owe) | Purchases count as money out, the card payment is 'Not an expense', refunds are negative | ✅ ready | – |
| `S07-euro.pdf` | A statement in euros | Currency stored as EUR | ✅ ready | – |
| `S08-special-characters.pdf` | Descriptions with accents, quotes and symbols | Saved exactly as printed | ✅ ready | – |
| `S09-big-amounts.pdf` | Amounts over a million | Stored to the cent | ✅ ready | – |
| `S10-zero-amount.pdf` | A 0.00 line (a waived fee) | Kept as a 0.00 row; math still checks out | ✅ ready | – |
| `S11-two-months.pdf` | A statement covering Oct 15 – Nov 14 | Rows land in both month tabs | ✅ ready | – |
| `S12-identical-twins.pdf` | Two identical coffees on the same day | Both are kept (both happened) | ✅ ready | – |
| `S13-locked-right-password.pdf` | Password-protected PDF, correct password typed | Opens and reads | ✅ ready | Dob-1990 |
| `S14-locked-no-password.pdf` | Password-protected PDF, no password given | Fails safely and asks for the password | 🔴 rejected | Dob-1990 |
| `S15-locked-wrong-password.pdf` | Password-protected PDF, wrong password typed | Fails safely and asks for the password | 🔴 rejected | Dob-1990 |
| `S16-locked-saved-password.pdf` | Password-protected PDF, password saved earlier in the Keychain | Opens automatically without asking | ✅ ready | Dob-1990 |
| `S27-not-a-statement.pdf` | A restaurant menu PDF uploaded by mistake | Politely rejected | 🔴 rejected | – |
| `S28-blank-pdf.pdf` | A blank PDF page | Politely rejected | 🔴 rejected | – |
| `S29-broken-file.pdf` | A corrupted / half-downloaded PDF | Rejected as unreadable | 🔴 rejected | – |
