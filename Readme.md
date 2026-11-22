<h1 align="center">💸 Where Did My Money Go?</h1>

<p align="center">
  <b>Upload your bank statement. Get 5 tidy Google Sheets.<br>
  Permanently lose the ability to say <i>"I honestly have no idea where it all went."</i></b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/AI-Claude%20Opus%205.5-D97757" alt="Claude Opus 5.5">
  <img src="https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white" alt="Streamlit">
  <img src="https://img.shields.io/badge/data-stays%20on%20your%20laptop-2ea44f" alt="Data stays local">
  <img src="https://img.shields.io/badge/financial%20advice-absolutely%20not-lightgrey" alt="Not financial advice">
</p>

<p align="center">
  <img src="https://api.memegen.link/images/fine/Bank_balance_after_one_weekend/This_is_fine.gif" width="460" alt="This is fine dog: 'Bank balance after one weekend'">
</p>

[Plan](Plan.md) · [Architecture](Architecture.md) · [Backend](Backend.md) · [DB](DB.md) · [Testing](TESTING.md) · [Reason](Reason.md)

---

## 🤔 What is this?

You know that PDF your bank emails you every month, the one you open, scroll, sigh at, and close?

**This app reads it for you.** It finds every transaction, checks the math against the bank's own balance (to the cent), works out what each payment was for, and files everything into **5 Google Sheets**, one per category, with a tab for every month:

| 🛒 Grocery | ✈️ Travel | 🔁 Subscriptions | 📈 Investments | 🏦 Savings |
|---|---|---|---|---|

Next month you upload the next statement, and the sheets just keep growing. Congratulations, you now have a financial history. Your accountant friend is proud of you.

<p align="center">
  <img src="https://api.memegen.link/images/drake/Typing_200_transactions_into_Excel_by_hand/Uploading_one_PDF_and_letting_the_robot_do_it.png" width="400" alt="Drake meme: no to typing 200 transactions into Excel, yes to uploading one PDF">
</p>

### Who is this for?

<p align="center">
  <img src="https://api.memegen.link/images/ds/Know_where_my_money_goes/Stay_happily_clueless/Me.png" width="360" alt="Daily struggle: Know where my money goes vs Stay happily clueless">
</p>

For people brave enough to press the left button. 🫡

---

## 😩 The problem

<p align="center">
  <img src="https://media.giphy.com/media/XIqCQx02E1U9W/200.gif" width="360" alt="Kermit typing frantically">
  <br><i>Me last month, copying 143 transactions into Excel by hand. Like an animal.</i>
</p>

- A statement tells you **what** happened, never **what it means**.
- Budgeting apps want your **bank password**. Hard pass.
- Spreadsheets by hand: fun for exactly one month, then abandoned forever.

<p align="center">
  <img src="https://api.memegen.link/images/rollsafe/Can't_have_a_spending_problem/If_you_never_open_your_statement.gif" width="400" alt="Roll Safe: can't have a spending problem if you never open your statement">
</p>

*Bold strategy. This app is here to ruin it.*

---

## 🪄 How it works (30-second version)

1. 📄 **You drop in a statement PDF.** Locked ones too: it remembers the password (securely, in your Mac's Keychain).
2. 🤖 **Claude (the AI) reads every row,** even on scanned statements.
3. 🧮 **The app checks the math.** Opening balance + money in − money out must equal what the bank printed, row by row. If one number is off, it tells you *exactly which row*.
4. 🗂️ **Every row gets a category.** Shops it has seen before are sorted instantly by saved rules. New ones go to the AI.
5. 👀 **You glance at the few rows it wasn't sure about.** Your fixes become rules, so it gets smarter every month.
6. 📊 **Sync**: rows land in the right Google Sheet, in the right month tab, and the totals update themselves.

<p align="center">
  <img src="https://api.memegen.link/images/gru/Upload_my_bank_statement/AI_sorts_every_expense/Find_out_cabs_cost_more_than_rent/Find_out_cabs_cost_more_than_rent.png" width="460" alt="Gru's plan: upload statement, AI sorts every expense, find out cabs cost more than rent">
</p>

---

## 🗂️ The 5 sheets

```
📗 Expenses – Grocery          ← one spreadsheet per category (×5)
   ├── Summary                 ← monthly totals (formulas, always correct)
   ├── 2026-11                 ← a tab per month, newest first
   ├── 2026-10
   └── …
```

| Sheet | What lands there |
|---|---|
| 🛒 **Grocery** | Supermarkets, grocery delivery, markets |
| ✈️ **Travel** | Cabs, ride-hailing, fuel, parking, tolls, trains, flights, hotels |
| 🔁 **Subscriptions** | Streaming, music, cloud, software, gym, phone and internet plans |
| 📈 **Investments** | Brokerage, mutual funds/SIPs, ETFs, stocks, crypto, retirement |
| 🏦 **Savings** | Transfers to your own savings, fixed or recurring deposits |

Everything else (rent, restaurants, shopping…) goes to **Other**. It stays visible in the app, and you can turn on a 6th "Other" sheet with one line in the settings.

<p align="center">
  <img src="https://api.memegen.link/images/harold/Opening_the_Grocery_sheet/After_one_quick_store_run.png" width="380" alt="Hide the Pain Harold: opening the Grocery sheet after one quick store run">
</p>

<p align="center">
  <img src="https://api.memegen.link/images/buzz/Subscriptions/Subscriptions_everywhere.gif" width="400" alt="Buzz Lightyear: Subscriptions, subscriptions everywhere">
  <br><i>Opening the Subscriptions sheet for the first time.</i>
</p>

<p align="center">
  <img src="https://api.memegen.link/images/stonks/Moved_50_bucks_to_Investments/Stonks.png" width="380" alt="Stonks: moved 50 bucks to Investments">
</p>

---

## 🐦 Wait, what's *not* an expense?

<p align="center">
  <img src="https://api.memegen.link/images/pigeon/Me/Moving_money_to_my_own_savings/Is_this_an_expense~q.png" width="420" alt="Is this a pigeon: Me, moving money to my own savings, is this an expense?">
</p>

**No.** Moving money between *your own* accounts isn't spending. The app knows that:

- **Salary, interest, money coming in** → *Not an expense* (never written to any sheet)
- **Paying your credit card bill** → *Not an expense*. Otherwise every card purchase would be counted **twice**. Upload the card statement itself to see what you actually bought.
- **Refunds** → a **negative** amount in the original category, so the month's total nets out
- **Investments and Savings** are money *set aside*, not spent, so the dashboard shows them separately and works out your **savings rate**

<p align="center">
  <img src="https://media.giphy.com/media/xT0xeJpnrWC4XWblEk/giphy-downsized.gif" width="320" alt="Mind blown">
  <br><i>Realizing that "spending" and "saving" are different numbers.</i>
</p>

<p align="center">
  <img src="https://media.giphy.com/media/67ThRZlYBvibtdF9JH/giphy-downsized.gif" width="320" alt="Bugs Bunny with a suitcase of money">
  <br><i>Me on payday. (Filed under "Not an expense". Enjoy it while it lasts.)</i>
</p>

---

## ✨ Features

- ✅ Reads **any bank or credit card PDF**: password-protected, scanned, multi-page
- ✅ **Math check to the cent**, pointing at the exact row if something's off
- ✅ **Zero duplicates**, even if you upload the same statement twice, or two overlapping ones
- ✅ **Learns from your corrections.** Fix a shop once and it's fixed forever.
- ✅ **5 Google Sheets × monthly tabs**, plus a self-updating Summary tab
- ✅ **Dashboard**: spending vs. set aside, savings rate, monthly chart, top shops
- ✅ **Alerts**: double charges, weirdly big charges, new subscriptions, sneaky price increases, free trials that turned paid, category spikes
- ✅ **Automation**: drop PDFs in a folder and they're processed on their own
- ✅ **Monthly summary** to Telegram (optional)
- ✅ **Cost log**: see exactly what the AI cost you (spoiler: very little)
- ✅ **206 automated tests** across 34 real-life statement scenarios, including deliberate AI mistakes it must catch ([TESTING.md](TESTING.md))
- ✅ **Your data stays on your laptop.** Details in [Privacy](#-privacy).

<p align="center">
  <img src="https://api.memegen.link/images/success/Uploaded_the_same_statement_twice/Zero_duplicates.png" width="360" alt="Success kid: uploaded the same statement twice, zero duplicates">
</p>

---

## 🚀 Quick start

<p align="center">
  <img src="https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif" width="120" alt="Loading spinner">
  <br><i>About 30–45 minutes, once. Most of it is clicking around Google Cloud.</i>
</p>

**1. Install**
```bash
cd ~/Documents/meet-project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

**2. Add your Claude API key** to `.env` (get one at platform.claude.com, and set a monthly spend limit while you're there):
```bash
ANTHROPIC_API_KEY=sk-ant-…
```

**3. Set up Google Sheets** (the 5-minute version; the very detailed version is in [Backend → Setup](Backend.md#4-setup-step-by-step)):
1. In Google Cloud, create a project, enable the **Google Sheets API**, create a **service account**, and download its JSON key as `service_account.json`.
2. Create 5 spreadsheets (`Expenses – Grocery`, …). Rename each first tab to **`Summary`** and share each with the service account's email as **Editor**.
3. Paste the 5 spreadsheet IDs (the long code in each URL) into `config.yaml`.

**4. Check everything**
```bash
python cli.py check
```

**5. Go!**
```bash
streamlit run app.py --server.address localhost     # the app → http://localhost:8501
# or, from the terminal:
python cli.py process ~/Downloads/statement.pdf
python cli.py sync
```

**Want to click around before setting up any keys?** There's a demo with 3 months of fake statements:
```bash
python scripts/demo.py
WDMMG_CONFIG=demo/config.yaml streamlit run app.py --server.address localhost
```

**Have a Claude key but no statement handy?**
```bash
python scripts/make_fake_statement.py        # creates data/inbox/fake_statement.pdf (fake data)
python cli.py process data/inbox/fake_statement.pdf --dry-run
```

---

## 🗓️ Your monthly routine (about 2 minutes)

1. Bank emails you a statement → drop it into the app (or into `data/inbox/` if automation is on).
2. Open **Review** and approve the few rows it wasn't sure about.
3. Click **Sync to Google Sheets**.
4. Open the **Dashboard** and feel things.

<p align="center">
  <img src="https://api.memegen.link/images/panik-kalm-panik/47_transactions_I_don't_remember/The_app_sorted_them_all/They're_all_food_delivery.png" width="360" alt="Panik kalm panik: 47 transactions I don't remember, the app sorted them all, they're all food delivery">
</p>

<p align="center">
  <img src="https://api.memegen.link/images/woman-cat/Me:_I_barely_spent_anything_this_month/The_Summary_tab:.png" width="440" alt="Woman yelling at cat: Me: I barely spent anything this month. The Summary tab:">
</p>

<p align="center">
  <img src="https://api.memegen.link/images/dbg/I'll_save_30~p_this_month/Saved_3~p.png" width="360" alt="Expectation vs reality: I'll save 30% this month, saved 3%">
  <br><i>The savings rate on the dashboard doesn't lie. It's rude like that.</i>
</p>

---

## 🧮 Does it actually get the numbers right?

Yes, and it **proves** it. Your statement prints a running balance after every row. The app replays every transaction from the opening balance and compares its result to the bank's number, row by row:

```
Opening balance 1,000.00
Row 1  Fresh Mart   −54.20  → expected   945.80, statement says   945.80 ✅
Row 2  Salary    +3,000.00  → expected 3,945.80, statement says 3,945.80 ✅
Row 3  City Cabs    −46.00  → expected 3,899.80, statement says 3,881.80 ❌
       → "Row 3: expected 3,899.80, statement shows 3,881.80"  (AI read 64.00 as 46.00)
```

If anything doesn't match, **nothing goes to your sheets** until you fix the row or approve the statement.

<p align="center">
  <img src="https://media.giphy.com/media/DYH297XiCS2Ck/200.gif" width="300" alt="Kermit flailing excitedly">
  <br><i>Me when the balances match to the cent.</i>
</p>

---

## 🚨 Alerts

The app quietly watches for:

| Alert | Example |
|---|---|
| 💥 Double charge | "City Cabs charged 64.00 twice within 2 days" |
| 📈 Unusually big charge | "Fresh Mart: 412.00 (usually about 55.00)" |
| 🆕 Big charge from a new shop | "First charge from MERCHANT 8812 LLC: 249.00" |
| 🔁 Forgotten subscription? | "GymCo charges you every month (about 29.99). A subscription you forgot about?" |
| 💸 Subscription price increase | "StreamFlix went from 12.99 to 15.99" |
| 🪤 Free trial turned paid | "CloudThing: 1.00 trial, then 49.99 12 days later" |
| 📊 Category spike | "Travel this month: 640.00, 2.1× your 3-month average" |

<p align="center">
  <img src="https://media.giphy.com/media/12XMGIWtrHBl5e/giphy-downsized.gif" width="320" alt="Michael Scott: No, God, please no">
  <br><i>Me reading "StreamFlix went from 12.99 to 15.99".</i>
</p>

---

## 🔒 Privacy

| What | Where it goes |
|---|---|
| Your statement PDFs and the database | **Your laptop only** (`data/`, never committed to git) |
| PDF passwords | **macOS Keychain only.** PDFs are unlocked *on your laptop* before anything is sent. |
| Statement pages | Sent to Claude to be read (encrypted connection) |
| Account numbers | **Last 4 digits only** in the database and sheets |
| Your Google Sheets | Only the 5 categories. Salary and transfers are never written there. |
| The web app | Reachable only from your own computer (`--server.address localhost`) |

<p align="center">
  <img src="https://media.giphy.com/media/fDO2Nk0ImzvvW/200.gif" width="320" alt="Grampa Simpson walks in and immediately walks back out">
  <br><i>Your bank data peeking at the public internet, then deciding to stay home.</i>
</p>

Full details: [Architecture → What leaves your computer](Architecture.md#8-what-leaves-your-computer).

---

## 💰 What it costs

| Thing | Cost |
|---|---|
| Reading a 5-page statement (Claude Opus 5.5) | ~10–25¢ |
| Categorizing | A few cents, and falling to ~0 as it learns your shops |
| Google Sheets | Free |
| Hosting | Free (it's your laptop) |
| **A normal month** | **Well under $1** |

<p align="center">
  <img src="https://api.memegen.link/images/money/An_app_that_finds_where_my_salary_went~q/Shut_up_and_take_my_money.gif" width="400" alt="Shut up and take my money">
</p>

Check what you've actually spent anytime with `python cli.py costs`.

<p align="center">
  <img src="https://api.memegen.link/images/cmm/Coffee_is_an_investment.png" width="380" alt="Change my mind: Coffee is an investment">
  <br><i>The app has reviewed your argument and filed coffee under <b>Other</b>.</i>
</p>

---

## ❓ FAQ (brutally honest edition)

**Will this make me rich?**
No. It will make you *informed*, which is cheaper and more painful.

<p align="center">
  <img src="https://api.memegen.link/images/fry/Not_sure_if_I'm_good_with_money/Or_just_never_open_my_statements.gif" width="380" alt="Futurama Fry: not sure if I'm good with money or just never open my statements">
</p>

**Can it cancel my gym membership?**
It can *find* it (Subscriptions sheet, every single month). Cancelling is on you.

<p align="center">
  <img src="https://api.memegen.link/images/mordor/One_does_not_simply/Cancel_a_gym_membership.png" width="380" alt="One does not simply cancel a gym membership">
</p>

**Why is "Other" so big?**
Restaurants and food delivery live in Other, not Grocery. Cooked food isn't groceries, no matter how hard you argue.

<p align="center">
  <img src="https://api.memegen.link/images/exit/Saving_money/Late--night_food_delivery/Me.png" width="380" alt="Left exit 12: Saving money vs Late-night food delivery, car labeled Me swerving">
</p>

**Can I edit the Google Sheets directly?**
Please don't. The sheets are a *mirror* of the app's database, and the next sync overwrites hand edits. Fix things in the app (Review or Transactions page) and they flow to the sheets automatically.

**The AI put something in the wrong category.**
Change it in the app and tick *"Remember my choice"*. That shop is sorted your way from then on.

**Does it work with my bank?**
Probably. It doesn't use per-bank templates; the AI reads the page like a human would. The math check catches anything it misreads.

**Is my data used to train anything?**
The app sends statement pages to the Claude API to be read. Check Anthropic's current data-handling terms for API usage if that matters to you (it should).

**Can my partner, roommate or cat use it too?**
Version 1 is one person, one laptop. The cat will have to wait.

---

## 🛠️ Command cheat sheet

| Command | What it does |
|---|---|
| `python cli.py check` | Checks your keys, sheets and folders |
| `python cli.py process FILE.pdf` | Read, check and categorize a statement (`--ask-password`, `--dry-run`) |
| `python cli.py inbox` | Process every PDF in `data/inbox/` |
| `python cli.py watch` | Keep watching `data/inbox/` and process new PDFs automatically |
| `python cli.py review` | List rows waiting for your OK |
| `python cli.py approve ID` | Accept a statement whose numbers didn't match (after checking it!) |
| `python cli.py sync` | Update Google Sheets |
| `python cli.py rebuild 2026-11` / `--all` | Rebuild sheet tabs from the database |
| `python cli.py status` | All statements and where they're up to |
| `python cli.py alerts` | Open alerts |
| `python cli.py summary --month 2026-11 [--send]` | Monthly summary (optionally sent to Telegram) |
| `python cli.py costs` | What the AI has cost you |
| `python cli.py rules` | Shops the app has learned |
| `python cli.py forget ID` | Delete a statement and its rows |
| `python cli.py backup` | Back up the database |
| `python cli.py password add NAME` | Save a PDF password in the Keychain (`list`, `remove` too) |
| `python -m pytest` | Run the 206 automated tests (free, no real APIs). See [TESTING.md](TESTING.md). |

---

## 🧯 Troubleshooting

| You see | Do this |
|---|---|
| "This PDF is locked" | Enter the password and tick **Remember**, or run `python cli.py password add mybank` once |
| "This doesn't look like a bank statement" | It's probably not. Check you uploaded the right PDF. |
| "Numbers don't match – check row 37" | Open **Statements**, compare row 37 with the PDF, fix it in **Transactions**, then approve |
| "Can't open the Grocery sheet" | Share that spreadsheet with the email in `service_account.json` (`client_email`) as **Editor** |
| "Claude is busy" | Wait a minute and try again. It's always safe to retry. |
| "No Claude API key found" | Check `.env` exists in the project folder and has `ANTHROPIC_API_KEY=sk-ant-…` |
| Sheets look wrong | `python cli.py rebuild --all` rebuilds them from the database |

---

## 🗺️ Roadmap

- [x] Read, check, categorize, review, sync
- [x] Dashboard, alerts, cost log
- [x] Folder automation and Telegram summary
- [ ] Fetch statements from Gmail automatically
- [ ] Privacy mode (remove account numbers before sending to the AI)
- [ ] Budgets per category, with a heads-up at 80%
- [ ] Ask questions in plain English ("How much on travel in Q3?")
- [ ] Match receipt photos to transactions

---

## 📚 Docs

| Doc | Read it if you want… |
|---|---|
| [Plan.md](Plan.md) | The what and why: goals, categories, screens, phases, risks |
| [Architecture.md](Architecture.md) | How it fits together, where your data goes, and the design decisions |
| [Backend.md](Backend.md) | Setup, every module explained, error handling, testing |
| [DB.md](DB.md) | Every table and column, how duplicates and sync work, backups |
| [TESTING.md](TESTING.md) | How it's tested: 34 real-life scenarios, fake statements, the bugs the tests caught, latest results |
| [Reason.md](Reason.md) | **Why this and not that**: every decision (business rules, stack, database, algorithms, security) with its trade-offs |

---

## 🙏 Credits

- Reading and categorizing by [Claude](https://www.anthropic.com/claude) (Anthropic)
- Built with Streamlit, gspread, pypdf, pandas, Plotly and Typer
- Memes generated with [memegen.link](https://memegen.link) · GIFs via [GIPHY](https://giphy.com)

> ⚖️ **Disclaimer:** This is a personal tracking tool, not financial, tax or investment advice. Always double-check important numbers against your actual statements. The app tries very hard. Your bank is still the source of truth.

<p align="center"><b>Now go find out where your money went. 🫡</b></p>
