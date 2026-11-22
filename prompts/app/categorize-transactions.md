# 🗂️ Prompt: sort transactions into categories

[← Prompts folder](../README.md) · [Read a statement](extract-statement.md) · **Sort into categories**

| | |
|---|---|
| **Status** | 🟢 **Live.** The app reads this file every time it starts. Editing the text between the markers changes what Claude is told. |
| **Used by** | `finance/categorize.py` → `CATEGORIZE_PROMPT` |
| **Sent** | Only for shops the app doesn't know yet, about 100 rows per request, as the *system prompt*. Shops matched by a saved rule or a keyword never reach Claude. |
| **Claude's job** | Put each row into exactly one category, give it a clean shop name, and say how sure it is. |

---

## The prompt

Only the text between the two markers is sent. Everything else in this file is notes for people.

<!-- prompt:start -->
```text
You sort personal bank transactions into exactly one category each.

Categories:
- Grocery: food and household supplies bought to take home (supermarkets, grocery
  delivery, markets).
- Travel: getting around and trips (cabs, ride-hailing, fuel, parking, tolls, trains,
  metro, flights, hotels).
- Subscriptions: recurring charges for a service (streaming, music, cloud storage,
  software, gym, phone and internet plans).
- Investments: money put into assets (brokerage, mutual funds, SIPs, ETFs, stocks,
  crypto, retirement contributions).
- Savings: money moved to the user's own savings account, fixed deposit or recurring deposit.
- Other: any other real spending (rent, restaurants, cafés, food delivery, shopping, bills,
  insurance, loan payments, healthcare, cash withdrawals, money sent to other people).
- Not an expense: money coming in (salary, interest, transfers in) and payments of the
  user's own credit card bill.

Rules:
- Amount is positive for money out and negative for money in.
- A refund (money in from a shop) keeps that shop's category.
- Money coming back from the user's own savings or investments keeps that category.
- merchant: a short, clean shop name, e.g. 'AMZN Mktp US*2K4L9' -> 'Amazon'.
- If the description is too vague to tell, choose 'Other' with low confidence.
  Do not guess.
```
<!-- prompt:end -->

---

## What else Claude receives with it

> 💡 These parts are fixed in the code, because the code depends on their exact shape.

**1. Your past corrections, added to the end of the prompt** (only if you've corrected any). Up to your 40 most recent fixes, so Claude makes the same choices you would:

```text
The user corrected these before. Make the same choices for similar rows:
"UBER *EATS 8812" → Other
"TRF TO RD A/C 4471" → Savings
```

**2. The rows to sort**, as a numbered table. Short numbers (1, 2, 3…) instead of long IDs, so Claude can't mistype them when it answers:

```text
n | date | amount | description
1 | 2026-11-03 | 54.20 | POS FRSHMRT CTY 0042
2 | 2026-11-05 | 15.99 | NETFLIX.COM
3 | 2026-11-07 | -20.00 | REFUND AMZN MKTP
```

**3. The form Claude must fill in** (from `finance/categorize.py`), one entry per row:

| Field | Meaning |
|---|---|
| `n` | The row number from the table |
| `merchant` | Short, clean shop name |
| `category` | Exactly one of: Grocery, Travel, Subscriptions, Investments, Savings, Other, Not an expense |
| `confidence` | `high`, `medium` or `low` |

---

## What happens to the answer

| Claude says | The app does |
|---|---|
| **high** confidence | Files the row, and **remembers the shop**, so next month it's sorted for free without asking Claude |
| **medium** or **low** | Files the row but puts it in your **Review** queue. It doesn't reach Google Sheets until you confirm it. |
| Skips a row | The row goes to Review as "Other, low" |
| A category not on the list | Impossible. The form only accepts the 7 names above. |

---

## Why each rule is there

| Rule | Why |
|---|---|
| Examples inside each category ("fuel, parking, tolls…") | The grey areas are where mistakes happen. Is fuel Travel? (Yes.) Is a gym Subscriptions? (Yes.) Is food delivery Grocery? (No, it's Other, because it's eating out.) Spelling them out gives the same answer every month. |
| "Not an expense" for card bill payments | Paying your card bill isn't new spending. The purchases are already on the card statement, so counting the payment would count them twice. |
| "A refund keeps that shop's category" | A refund from a supermarket should *reduce* Grocery, not appear as income. |
| "Money coming back from savings… keeps that category" | Taking 500 out of your savings is negative Savings, not salary. |
| The `merchant` example | Turns bank gibberish into names you'd recognize on the dashboard and in Google Sheets. |
| "Too vague… 'Other' with low confidence. Do not guess." | A confident wrong answer goes straight to your sheets, but an honest "not sure" comes to you for review. That's the whole point of the review queue. |

The business rules behind these choices are explained in [Reason §1](../../Reason.md#1-product-and-business-rules).

---

## Editing it safely

1. Change only the text **between** `<!-- prompt:start -->` and `<!-- prompt:end -->`. Keep the ` ```text ` fence lines.
2. **Keep all 7 category names** spelled exactly as they are. Claude's answer must use one of them. The free tests fail if one goes missing.
3. Run the free tests: `python -m pytest`
4. Measure accuracy on your own labeled transactions (costs a few cents): `python scripts/eval_categories.py`. It prints accuracy and the most common mix-ups. Keep the change only if the number went up.
5. Restart the web app, since prompts are read once at startup.

If you break something: `git checkout -- prompts/app/categorize-transactions.md` puts it back.

**Good edits:** move a grey area to where *you* want it (e.g. add "pharmacy" to Grocery if that's how you think of it), or add your country's terms ("UPI", "NEFT to self").
**Better than editing the prompt** for a single shop: correct it once in the Review page with "remember my choice" ticked. That saves a rule, which is free, instant and always wins over Claude.
