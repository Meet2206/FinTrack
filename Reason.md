# 🤔 Reason: why this, and not that

[Readme](Readme.md) · [Plan](Plan.md) · [Architecture](Architecture.md) · [Backend](Backend.md) · [DB](DB.md) · [Testing](TESTING.md) · **Reason**

| | |
|---|---|
| **What this document is** | Every significant decision in the project: what we chose, what we didn't, **why**, what it costs us, and when we'd change our mind. It covers business rules, architecture, tech stack, database, algorithms, security, reliability, user experience, testing and cost. |
| **Who it's for** | Everyone. Each decision starts in plain English. Jargon is explained the first time it appears. |
| **How to read it** | Skim the [index](#index), jump to what you're curious about. Every decision uses the same card. |

Every decision uses this card:

| | |
|---|---|
| **Chose** | what we did |
| **Over** | the realistic alternatives we considered |
| **Why** | the reasons, most important first |
| **Trade-off** | what we give up (there's always something) |
| **Revisit when** | the situation in which we'd change our mind |

---

## Index

1. [Product and business rules](#1-product-and-business-rules): how statements get in, the categories, what counts as spending, months, review
2. [Architecture](#2-architecture): how the pieces fit together
3. [Tech stack](#3-tech-stack): language, AI model, libraries
4. [Database design](#4-database-design): how records are stored
5. [Algorithms](#5-algorithms): the math check, reading PDFs, categorizing, alerts, sync
6. [Security and privacy](#6-security-and-privacy)
7. [Reliability and error handling](#7-reliability-and-error-handling)
8. [User experience](#8-user-experience)
9. [Testing](#9-testing)
10. [Cost](#10-cost)
11. [Deliberately postponed](#11-deliberately-postponed): good ideas we said "not yet" to

---

## 1. Product and business rules

### 1.1 Statements come in as PDF uploads
| | |
|---|---|
| **Chose** | You upload the PDF statement your bank already sends you |
| **Over** | Logging into your bank automatically (screen-scraping) · bank-connection services (Plaid and similar "aggregators") · CSV exports · typing transactions by hand |
| **Why** | **Every** bank produces a PDF statement, and it's the official record. No bank password ever touches the app. Aggregators cost money, cover only some banks and countries, and hold ongoing access to your accounts. Screen-scraping breaks whenever the bank changes its website and is a security risk. CSV exports differ per bank and often aren't available for credit cards. |
| **Trade-off** | Not real-time: you see a month when its statement arrives. One manual step (drop the PDF), reduced to zero by the inbox folder ([5.16](#516-wait-until-a-dropped-file-stops-growing)). |
| **Revisit when** | You want daily updates, and an aggregator supports your bank at a price you accept. Its rows would flow into the same ledger. |

### 1.2 Five categories, plus "Other" and "Not an expense"
| | |
|---|---|
| **Chose** | Grocery, Travel, Subscriptions, Investments, Savings, plus two helpers: **Other** (all remaining spending) and **Not an expense** (money in, and money moving between your own accounts) |
| **Over** | 20+ detailed categories (like most budgeting apps) · only the five, silently dropping everything else |
| **Why** | The five are what you asked to track, each with its own sheet. More categories mean more AI disagreements and more review work for little extra insight. But dropping everything else would make totals lie: rent and restaurants are real spending. "Other" keeps the full picture honest, and "Not an expense" stops salary and transfers from looking like spending. |
| **Trade-off** | "Other" is a big bucket (rent, dining, shopping all together). |
| **Revisit when** | "Other" is consistently large and you want it split. Adding a category is a settings change plus one line in the database's list of allowed values. |

### 1.3 Investments and Savings are "set aside", not "spent"
| | |
|---|---|
| **Chose** | The dashboard shows **Spent** (Grocery + Travel + Subscriptions + Other) separately from **Set aside** (Investments + Savings), plus a **savings rate** = set aside ÷ money in |
| **Over** | Treating everything that leaves the account as spending · savings rate = (income − spending) ÷ income |
| **Why** | Moving 500 to savings isn't the same as spending 500. Mixing them would punish you for saving. Measuring what you *actively* set aside is direct and visible. The "(income − spending)" version counts money that just sat in your current account as "saved". |
| **Trade-off** | Money left in your current account doesn't count towards the savings rate. |
| **Revisit when** | You'd rather track net worth (balances) than flows (transactions). That's a different feature. |

### 1.4 Paying your credit card bill is "Not an expense"
| | |
|---|---|
| **Chose** | "CREDIT CARD PAYMENT" from your bank account = Not an expense. The purchases themselves come from the card statement. |
| **Over** | Counting the bill payment as spending |
| **Why** | Otherwise every card purchase would be counted **twice**: once as the purchase on the card statement, again as the bill payment from the bank. This is the most common mistake in home-made budgets. A test checks the flight is counted exactly once. |
| **Trade-off** | If you never upload the card statement, card spending is invisible (the payment isn't counted). |
| **Revisit when** | Never for the rule itself. The Plan suggests uploading card statements too. |

### 1.5 Refunds are negative amounts in the original category
| | |
|---|---|
| **Chose** | A Fresh Mart refund of 8.99 is **−8.99 in Grocery** |
| **Over** | Treating refunds as income · a separate "Refunds" category |
| **Why** | You care about what groceries *really* cost you this month. A refund undoes part of a purchase, it isn't income. With a separate category, the Grocery total would be overstated. |
| **Trade-off** | A month's category total can be lower than the sum of its purchases. That's correct, but can surprise you. |
| **Revisit when** | Never. This is standard accounting practice (a "contra" entry). |

### 1.6 Money coming *back* from savings or investments is negative in that category
| | |
|---|---|
| **Chose** | Withdrawing 200 from savings = **−200 in Savings** |
| **Over** | Counting it as income (Not an expense) |
| **Why** | So the Savings total shows what you *really* set aside this month (net). Otherwise moving money back and forth would inflate both "saved" and "money in". |
| **Trade-off** | The AI must recognize "transfer from my own savings". When unsure, it flags the row for review. |
| **Revisit when** | You want gross flows. That's a report, not a rule change. |

### 1.7 Rows go into a month by transaction date
| | |
|---|---|
| **Chose** | The **transaction date** decides the month tab. A statement from Oct 15 to Nov 14 fills both October and November. |
| **Over** | The statement's period or closing date · the posting date |
| **Why** | Banks cut statements on different days (often mid-month). Using statement dates would make "November" mean different things for different accounts, and comparisons would be meaningless. The transaction date is when you actually spent the money. |
| **Trade-off** | A month is only complete once every statement covering it is uploaded. |
| **Revisit when** | Never. Upload the next statement and the month completes itself. |

### 1.8 Default answers for the grey areas
| | |
|---|---|
| **Chose** | Restaurants and food delivery → Other. Fuel, parking, tolls → Travel. Phone, internet, gym → Subscriptions. Insurance and loans → Other. Cash withdrawals → Other. |
| **Over** | Leaving them for the AI to decide case by case |
| **Why** | Consistency. If the rules aren't written down, the same kind of payment lands in different places in different months, and month-to-month comparisons become noise. They're written into the AI's instructions and are easy to override (your corrections become rules). |
| **Trade-off** | These are opinions. You may see pizza delivery differently. |
| **Revisit when** | You disagree. Fix one row with "remember" ticked and your choice wins from then on ([5.9](#59-categorization-order-your-rules--saved-rules--keywords--ai)). |

### 1.9 You review only the rows the AI is unsure about
| | |
|---|---|
| **Chose** | Rows with medium or low AI confidence wait in a review queue. Everything else goes straight through. |
| **Over** | Reviewing every row · reviewing nothing |
| **Why** | Reviewing everything is the manual work we're trying to remove. Reviewing nothing lets mistakes slip into your sheets silently. Asking only where the AI is unsure puts your attention where it's worth the most, and it shrinks every month as rules are learned. |
| **Trade-off** | A confidently wrong AI answer skips review. That's rare for obvious shops, and fixable at any time on the Transactions page. |
| **Revisit when** | You want to be stricter or looser. `review_if_confidence` in config.yaml can be `[low]`, `[low, medium]`, `[low, medium, high]` or `[]`. All four are tested. |

### 1.10 If the math doesn't add up, the *whole* statement is held
| | |
|---|---|
| **Chose** | One mismatch holds **every** row of that statement back from Google Sheets |
| **Over** | Holding only the row that failed |
| **Why** | A misread usually isn't alone: if the AI misread one number, nearby numbers on the same page deserve suspicion too. Wrong financial data is worse than late data. It's also easier to understand: "this statement needs a look" rather than a scattering of held rows. |
| **Trade-off** | A single bad row delays the whole statement until you fix or approve it (a couple of clicks). |
| **Revisit when** | Statements are very long and misreads frequent (then hold just that page group). The tests show misreads are caught reliably, so this hasn't been needed. |

### 1.11 You can approve a statement that doesn't add up
| | |
|---|---|
| **Chose** | An "I've checked it: approve" button for mismatched statements |
| **Over** | Blocking them forever |
| **Why** | Sometimes the *PDF* is the odd one out: a bank prints a rounded balance, or a statement prints no balances at all. You, looking at the PDF, are the final authority. Approving is recorded (`approved_by_user`), so it's never silent. |
| **Trade-off** | A careless approval could let a misread through. The button text and docs ask you to compare with the PDF first. |
| **Revisit when** | Never. An escape hatch the user controls is essential. |

### 1.12 No currency conversion
| | |
|---|---|
| **Chose** | Each row keeps its original currency. Totals assume one main currency. |
| **Over** | Converting everything to a home currency with exchange rates |
| **Why** | Conversion needs a rate source (another service), a rule for *which* day's rate, and creates numbers that don't match your statements. Most people's statements are in one currency. |
| **Trade-off** | Mixed-currency accounts would produce mixed totals. |
| **Revisit when** | You add an account in another currency. It's listed in Plan → Phase 7. |

### 1.13 Alerts are plain arithmetic, not AI
| | |
|---|---|
| **Chose** | Seven fixed rules computed with pandas (a spreadsheet-like data library) |
| **Over** | Asking the AI "does anything look suspicious?" · statistical anomaly detection |
| **Why** | Fixed rules are **free, instant, explainable** ("3× your usual" is something you can check yourself) and **predictable** (the same data always gives the same alerts). An AI could invent concerns, would cost money on every statement, and couldn't be tested on both sides of a threshold. Statistical models need lots of history that a personal account doesn't have. |
| **Trade-off** | The rules only catch what they're designed for. Thresholds are explained in [5.15](#515-alert-rules-and-their-thresholds). |
| **Revisit when** | There's a pattern you want caught that a simple rule can't express. |

### 1.14 One person, one laptop
| | |
|---|---|
| **Chose** | A single-user tool that runs on your computer |
| **Over** | A web service with accounts, a family/shared version |
| **Why** | Financial data is the most sensitive data most people have. A multi-user service needs logins, encryption at rest, hosting, backups, monitoring and legal care, which is 10× the work for a personal tool. Local means private by default and free to run. |
| **Trade-off** | No phone access, and automation only runs while the laptop is on. |
| **Revisit when** | A partner needs access. Then put it on a home mini-computer with a login screen ([Architecture §12](Architecture.md#12-deployment-where-it-runs)). |

---

## 2. Architecture

### 2.1 One engine, three doors
| | |
|---|---|
| **Chose** | All logic in the `finance/` package. The web app, command line and folder watcher are thin "doors" that call it. |
| **Over** | Putting logic inside the web pages |
| **Why** | One copy of every rule, so the web app and the command line can never disagree. The engine can be tested without a browser, and new doors (a phone shortcut, an email fetcher) don't touch the logic. |
| **Trade-off** | A little more structure than a single script. |
| **Revisit when** | Never. This is the backbone. |

### 2.2 The database is the master, Google Sheets is a mirror
| | |
|---|---|
| **Chose** | SQLite holds the truth. Sheets are generated from it and treated as read-only. |
| **Over** | Using Google Sheets as the database · two-way sync (edit in either place) |
| **Why** | Two editable copies eventually disagree, and then which one is right? With one master, the sheets can be rebuilt perfectly at any time, duplicates are prevented by the database, and Sheets can't express rules like "this transaction ID is unique". Two-way sync is one of the hardest problems in software (conflicts, merges, deletions). |
| **Trade-off** | Hand edits in Google Sheets get overwritten. Edit in the app instead. |
| **Revisit when** | Someone who never uses the app must edit categories. Then add a deliberate "import corrections from Sheets" step, never silent two-way sync. |

### 2.3 Sync rebuilds whole month tabs
| | |
|---|---|
| **Chose** | For every affected (category, month) tab: clear it, rewrite it from the database. Untouched tabs aren't written at all. |
| **Over** | Appending new rows · rebuilding every tab on every sync |
| **Why** | Appending is fragile: a crash half-way leaves you unsure what was written, and a row that changes category must be found and deleted elsewhere. Rebuilding is **idempotent** (running it twice gives the same result), so a failed sync is fixed by simply running it again. Rebuilding only the affected tabs keeps it fast and gentle on Google's rate limits (a test proves an unchanged sync makes zero writes). |
| **Trade-off** | It writes a whole month (a few hundred rows) even when one row changed. Negligible at personal scale. |
| **Revisit when** | Tabs hold tens of thousands of rows. |

### 2.4 Local-first, no server
| | |
|---|---|
| **Chose** | Everything runs on your laptop. Only Claude and Google are contacted. |
| **Over** | A cloud server (AWS, Render, etc.) |
| **Why** | Privacy, zero hosting cost, nothing exposed to the internet, nothing to patch. See [1.14](#114-one-person-one-laptop). |
| **Trade-off** | Automation needs the laptop to be on. |
| **Revisit when** | You want 24/7 automation. Use an always-on home device. |

### 2.5 A straightforward pipeline, not a job queue
| | |
|---|---|
| **Chose** | `process_statement()` runs the steps one after another, in plain Python |
| **Over** | A task queue (Celery, Redis), async workers |
| **Why** | A personal app processes a few statements a month. A queue adds servers, configuration and failure modes for no benefit. Statuses in the database already give us "where is it up to?" and safe retries. |
| **Trade-off** | You wait 1–2 minutes while a statement is read (with a progress spinner). |
| **Revisit when** | Many users or many statements at once. |

---

## 3. Tech stack

### 3.1 Python
| | |
|---|---|
| **Chose** | Python 3.12+ |
| **Over** | JavaScript/TypeScript · Go · Java |
| **Why** | The best-supported language for AI SDKs, PDFs, data analysis (pandas) and Google APIs. Easy to read for a learning project. Streamlit lets the same language build the web app. |
| **Trade-off** | Not the fastest language, but speed is limited by the AI (seconds), not our code (milliseconds). |
| **Revisit when** | It becomes a public web product with a rich interface. Then a TypeScript front-end would call this same engine. |

### 3.2 Claude Opus 5.5 as the AI
| | |
|---|---|
| **Chose** | Claude Opus 5.5 (`claude-opus-5-5`) for both reading and categorizing |
| **Over** | Smaller, cheaper models (Claude Sonnet 5.5, Haiku 5.5) · other providers · a local model on your laptop (e.g. via Ollama) |
| **Why** | Reading financial documents is a "must be right" job. The most capable model gives the fewest misreads and handles messy layouts and scanned pages. At $4 per million tokens read and $20 per million written, a month costs well under $1, because rules make repeat shops free. Local models need a powerful computer and read tables less reliably. |
| **Trade-off** | Higher cost per call than smaller models. |
| **Revisit when** | `scripts/eval_categories.py` shows a cheaper model categorizes your transactions just as accurately. Categorizing is the easiest place to save. Change `model:` in config.yaml. |

### 3.3 Structured outputs with Pydantic "forms"
| | |
|---|---|
| **Chose** | `client.messages.parse(..., output_format=StatementChunk)`: Claude must fill in a strict form, and Pydantic (a data-validation library) checks every field |
| **Over** | Asking for JSON in the prompt and hoping · tool calls used as a JSON trick · parsing free text with patterns |
| **Why** | The API constrains the answer to our schema, and the SDK validates it into typed Python objects. No "the AI added a comment before the JSON" failures, and no hand-written parsing. If the answer is cut off, validation fails loudly and we retry with fewer pages. |
| **Trade-off** | The form must use schema features the API supports (we keep it simple: strings, numbers, nulls, lists, fixed choices). |
| **Revisit when** | Never. This is the right tool for extraction. |

### 3.4 Send the PDF pages straight to Claude
| | |
|---|---|
| **Chose** | Send page groups as PDFs. Claude sees the text *and* the layout. |
| **Over** | Extract text on the laptop first (pdfplumber), then send text · traditional OCR (Tesseract) · a hand-written template per bank |
| **Why** | Works with **any** bank from day one, including scanned (image-only) statements and complex tables where text extraction scrambles the columns. Per-bank templates break when a bank redesigns its statement. The math check catches any misread. |
| **Trade-off** | Costs a few cents per statement, and the full page (including your name and address) goes to the AI provider ([6.4](#64-v1-sends-whole-pages-to-claude)). |
| **Revisit when** | One bank makes up most of your statements: a free, deterministic pdfplumber reader for that bank, with Claude as fallback (Plan → Phase 7). |

### 3.5 pypdf for PDF handling
| | |
|---|---|
| **Chose** | pypdf (+ `cryptography` for encrypted PDFs) |
| **Over** | PyMuPDF · pdfplumber · qpdf / command-line tools |
| **Why** | Pure Python with a permissive license, so it installs anywhere with no system dependencies. It does exactly what we need: open, decrypt (including AES-256), split into page groups, extract text for tests. PyMuPDF is faster but AGPL-licensed (restrictive for redistribution). pdfplumber is for extracting tables, which Claude does for us. |
| **Trade-off** | Slower than PyMuPDF on huge files. Irrelevant for statements. |
| **Revisit when** | We add the local "fast path" reader (then pdfplumber). |

### 3.6 SQLite for the database
| | |
|---|---|
| **Chose** | SQLite: a full database in one file (`data/ledger.db`) |
| **Over** | PostgreSQL / MySQL · CSV or JSON files · Google Sheets as the database · DuckDB |
| **Why** | Zero setup (built into Python), one file to back up, private, very reliable (writes are all-or-nothing), and it enforces rules we depend on: unique fingerprints, allowed categories, links between tables. A server database is overkill for one person. CSV/JSON files can't enforce uniqueness and corrupt easily if a write is interrupted. DuckDB is superb for analysis but less suited to many small updates. |
| **Trade-off** | One writer at a time (fine for one person), and not reachable over a network. |
| **Revisit when** | Multiple people or devices write at once. Then PostgreSQL, and only `ledger.py` changes. |

### 3.7 Plain SQL instead of an ORM
| | |
|---|---|
| **Chose** | Hand-written SQL in one file (`ledger.py`) using Python's built-in `sqlite3` |
| **Over** | An ORM (SQLAlchemy, Django ORM): a library that turns tables into Python classes |
| **Why** | The data model is small (7 tables), and several queries are easier to read and tune as SQL (sync bookkeeping, conditional updates, partial indexes). No extra dependency, nothing hidden. Keeping all SQL in one file gives the same isolation an ORM would. |
| **Trade-off** | Switching databases means checking the SQL by hand. |
| **Revisit when** | The model grows a lot, or we move to PostgreSQL with many developers. |

### 3.8 gspread for Google Sheets
| | |
|---|---|
| **Chose** | gspread |
| **Over** | Google's official `google-api-python-client` · Google Apps Script |
| **Why** | gspread wraps the Sheets API in a simple, well-maintained library: open by ID, add, clear, update, reorder tabs, plus built-in back-off when Google says "slow down". The official client is much more verbose for the same work. Apps Script would split the logic across two languages and two places. |
| **Trade-off** | One more dependency. |
| **Revisit when** | We need Sheets features gspread doesn't cover (charts, advanced formatting). |

### 3.9 A Google "service account" (robot user)
| | |
|---|---|
| **Chose** | A service account that can only open the 5 spreadsheets you share with it |
| **Over** | Logging in as you (OAuth, the "Sign in with Google" flow) |
| **Why** | **Least privilege**: the robot can't see the rest of your Drive or Gmail. No browser login, so it works unattended for automation. No tokens expiring every few days. |
| **Trade-off** | One-time setup in Google Cloud (Backend → Setup, step 4), and you must share each sheet with the robot. |
| **Revisit when** | The app should *create* spreadsheets in your Drive for you. |

### 3.10 Streamlit for the web app
| | |
|---|---|
| **Chose** | Streamlit: web pages written as short Python scripts |
| **Over** | React + FastAPI · Flask or Django templates · Gradio · a desktop app (Tkinter/PyQt) · Jupyter notebooks |
| **Why** | One developer can build real, interactive screens (file upload, editable tables, charts) in Python alone, with no JavaScript, HTML or CSS. Ideal for a personal data tool. It ships a headless tester, so every page is automatically tested. React + an API means two codebases. Desktop toolkits are dated and harder to test. Gradio is aimed at AI demos. |
| **Trade-off** | Less control over the look, and every click reruns the page script. Fine for a single user. |
| **Revisit when** | It becomes a polished public product. The engine stays and a new front-end calls it. |

### 3.11 Typer for the command line
| | |
|---|---|
| **Chose** | Typer (+ Rich for tables and colors) |
| **Over** | Python's built-in argparse · click |
| **Why** | Commands are ordinary functions with type hints, and help text writes itself. It's built on click (battle-tested) with less boilerplate, and has a test runner we use for all 16 commands. Rich makes tables readable. |
| **Trade-off** | Two dependencies instead of zero. |
| **Revisit when** | Never, for this size of tool. |

### 3.12 Plotly for charts
| | |
|---|---|
| **Chose** | Plotly (stacked monthly bar chart) |
| **Over** | Streamlit's built-in charts · matplotlib · Altair |
| **Why** | Interactive (hover shows exact amounts, click the legend to hide a category) with one line of code. Streamlit's built-ins are too limited for stacked categories, and matplotlib produces static images. |
| **Trade-off** | A larger library. |
| **Revisit when** | Never. |

### 3.13 pandas for alerts and reports
| | |
|---|---|
| **Chose** | pandas |
| **Over** | Plain Python loops · polars |
| **Why** | Grouping by shop, time gaps between charges, medians, monthly totals: pandas expresses these directly and readably, and it's what Streamlit tables expect. polars is faster but the data is tiny, and pandas is more familiar. |
| **Trade-off** | A heavy dependency for a few calculations. |
| **Revisit when** | Never, at this scale. |

### 3.14 Settings in YAML, secrets in .env
| | |
|---|---|
| **Chose** | `config.yaml` for settings (validated by Pydantic), `.env` for secrets, the Keychain for PDF passwords |
| **Over** | Everything in environment variables · TOML / INI / JSON · settings inside the database |
| **Why** | YAML is the friendliest for humans to edit (comments, lists, nesting). Pydantic gives instant, readable errors ("pages_per_chunk: three" → *problem in config.yaml*). Keeping secrets separate means the settings file can be read, shown or shared without leaking keys. |
| **Trade-off** | YAML is picky about indentation. Mitigated by clear error messages and a commented example file. |
| **Revisit when** | Never. |

### 3.15 PDF passwords in the macOS Keychain
| | |
|---|---|
| **Chose** | `keyring`, which stores passwords in the operating system's secure Keychain. Saved passwords are tried automatically. |
| **Over** | A plain text file · environment variables · asking every time |
| **Why** | The Keychain is encrypted and locked to your user account. Plain text is how passwords leak. Asking every month is annoying and leads people to weaken their passwords. Trying all saved passwords means you never pick one. |
| **Trade-off** | `keyring` can't list entries, so we keep a separate Keychain entry with just the *names* you've saved. |
| **Revisit when** | Running on a server without a Keychain. Use an encrypted secrets file there. |

### 3.16 An inbox folder + watchdog for automation
| | |
|---|---|
| **Chose** | Drop PDFs into `data/inbox/`. `cli.py watch` reacts instantly (watchdog, file-system events), and `cli.py inbox` processes once (for a scheduled job). Results move to `done/` or `failed/`. |
| **Over** | Polling the folder in a loop · scheduled jobs only · fetching from Gmail directly |
| **Why** | A folder is the simplest universal interface: your browser downloads there, or a Mail rule saves attachments there. Watching for events is instant and uses no CPU while idle. Moving files to done/failed makes the folder's state obvious at a glance. Direct Gmail fetching needs Google OAuth and per-bank email rules (postponed, [11](#11-deliberately-postponed)). |
| **Trade-off** | You (or a Mail rule) still have to get the PDF into the folder. |
| **Revisit when** | We add the Gmail fetcher. It will simply drop files into the same inbox. |

### 3.17 Telegram for the monthly summary
| | |
|---|---|
| **Chose** | Telegram bot messages (optional) |
| **Over** | Email (SMTP) · Slack · SMS |
| **Why** | A free bot takes 2 minutes to create, and sending is one web request with no extra library. Email needs SMTP credentials and often lands in spam. SMS costs money. Slack is for teams. |
| **Trade-off** | You need Telegram. |
| **Revisit when** | You prefer email: add an SMTP sender beside `send_telegram()`. |

---

## 4. Database design

### 4.1 One signed amount column
| | |
|---|---|
| **Chose** | `amount`: **positive = money out, negative = money in** |
| **Over** | Separate "debit" and "credit" columns |
| **Why** | Summing a category gives what you actually spent, with refunds netted out ([1.5](#15-refunds-are-negative-amounts-in-the-original-category)). One column means simpler totals, charts and sheets. "Out = positive" matches how people think about spending. |
| **Trade-off** | The opposite of the accounting convention, where credits to your account are positive. Documented everywhere it matters. |
| **Revisit when** | Never. |

### 4.2 Money as rounded decimals, compared with a 1-cent tolerance
| | |
|---|---|
| **Chose** | SQLite `REAL`, rounded to 2 decimals on save. The math check rounds at every step and allows 0.01 of difference. |
| **Over** | Whole cents in integers (the textbook choice) · exact decimals stored as text |
| **Why** | Every value comes from a printed statement (2 decimals) and we only add and subtract, so rounding each step keeps results exact to the cent. It keeps the code, the AI's numbers, pandas and Google Sheets all in the same plain number type. |
| **Trade-off** | Floating-point numbers can't represent some decimals exactly. Harmless with rounding and a tolerance, but integer cents would be stricter. |
| **Revisit when** | We add currency conversion or interest calculations (multiplication and division). Then switch to integer cents in a migration. |

### 4.3 Dates as text `YYYY-MM-DD`, months as a calculated column
| | |
|---|---|
| **Chose** | ISO text dates, plus `month` as a **generated column**: `substr(txn_date, 1, 7)`, computed by the database itself |
| **Over** | Unix timestamps · storing month separately |
| **Why** | ISO text sorts correctly, reads clearly in any tool, and can't be misread (no 03/04 ambiguity). A generated month can never disagree with its date, even after you fix a misread date. |
| **Trade-off** | Date arithmetic happens in Python or pandas, not SQL. |
| **Revisit when** | Never. |

### 4.4 Transaction ID = a fingerprint of the content
| | |
|---|---|
| **Chose** | `id` = the first 16 characters of SHA-256 over (account, date, money out, money in, normalized description, occurrence counter) |
| **Over** | Auto-numbered IDs plus a uniqueness rule on several columns · trusting the bank's reference numbers |
| **Why** | The **same transaction always gets the same ID**, whichever statement or upload it came from. Duplicates are then impossible by construction: the database rejects a second copy (`INSERT OR IGNORE`). Bank reference numbers aren't printed consistently, and many statements have none. |
| **Trade-off** | If the AI reads a description differently in two overlapping statements, the IDs differ. Normalization ([4.5](#45-normalizing-descriptions-and-counting-identical-twins)) makes this rare, and the math check would flag a duplicated row. |
| **Revisit when** | Banks give reliable unique IDs, as aggregator data does. |

### 4.5 Normalizing descriptions and counting identical twins
| | |
|---|---|
| **Chose** | In the fingerprint, descriptions are lowercased and reduced to letters and digits. A counter numbers identical rows in the same statement (\|1, \|2). |
| **Over** | Using descriptions as printed · dropping identical rows as duplicates |
| **Why** | `POS 4471  FRSHMRT*CTY` and `POS 4471 FRSHMRT CTY` are the same transaction, read slightly differently. Two identical coffees on the same day both *really happened*, and dropping one would understate spending. Tests cover both. |
| **Trade-off** | Two genuinely different shops whose names differ only in punctuation would collide. Vanishingly unlikely on the same day for the same amount. |
| **Revisit when** | Never. |

### 4.6 An account = type + last 4 digits
| | |
|---|---|
| **Chose** | Accounts are identified by (bank or card, last 4 digits) |
| **Over** | Bank name + last 4 · the full account number |
| **Why** | The full number is never stored, for privacy ([6.2](#62-only-the-last-4-digits-are-stored)). The bank name as read by the AI varies ("EXAMPLE BANK N.A." vs "Example Bank"), which would split one account into two. |
| **Trade-off** | Two of your accounts of the same type ending in the same 4 digits would merge. Rare. A nickname column exists for the future. |
| **Revisit when** | It happens to you. |

### 4.7 Sync bookkeeping lives on each row
| | |
|---|---|
| **Chose** | Three columns: `synced_at` (empty = Sheets need updating), `synced_category` and `synced_month` (which tab the row was last written to) |
| **Over** | A separate sync-log table · one "dirty" flag |
| **Why** | A dirty flag tells you *that* something changed, but not *where the row used to be*, and that's exactly the tab that must be cleaned when a row moves category or month. Keeping it on the row means one simple query answers "what must be rebuilt?". `synced_month` was added (migration 002) after a test showed a date fix left a stale copy in the old month's tab. |
| **Trade-off** | Three extra columns. |
| **Revisit when** | Never. |

### 4.8 Statuses as text, checked by the database
| | |
|---|---|
| **Chose** | `status TEXT CHECK (status IN ('uploaded', 'processing', 'mismatch', 'ready', 'synced', 'failed'))` |
| **Over** | Numeric codes · a separate statuses table |
| **Why** | Readable anywhere (in a database viewer, logs, tests), and the database rejects typos. A lookup table is ceremony for six fixed values. |
| **Trade-off** | Adding a status needs a migration. |
| **Revisit when** | Never. |

### 4.9 Numbered SQL migrations
| | |
|---|---|
| **Chose** | Numbered SQL files (`001_init.sql`, `002_synced_month.sql`). The database remembers its version (`PRAGMA user_version`). Pending upgrades run at start-up, **after an automatic backup**. |
| **Over** | Alembic (a migration framework) · editing the database by hand |
| **Why** | Just a few lines of code, transparent (you can read each upgrade), and tested: an old version-1 database is upgraded in the tests. Alembic is built for ORMs and teams, which is too much here. |
| **Trade-off** | No automatic downgrades. Restore a backup instead. |
| **Revisit when** | We move to PostgreSQL with several developers. |

### 4.10 Foreign keys, cascading deletes, WAL mode, partial indexes
| | |
|---|---|
| **Chose** | Foreign keys on. Deleting a statement deletes its rows and alerts, but keeps its AI cost history (`ON DELETE SET NULL`). Write-ahead logging (WAL). Partial indexes for "unsynced" and "needs review". |
| **Over** | Manual clean-up · default journal mode · plain indexes |
| **Why** | The database enforces consistency, so "forget a statement" can't leave orphans. WAL makes writes safer and lets the web app read while something else writes. Partial indexes stay tiny because they only cover the few rows waiting for sync or review. |
| **Trade-off** | None worth mentioning. |
| **Revisit when** | Never. |

### 4.11 Keep a copy of every processed PDF
| | |
|---|---|
| **Chose** | Copy each uploaded PDF to `data/statements/` (named by fingerprint) |
| **Over** | Deleting PDFs after processing |
| **Why** | Lets you compare a flagged row with the original (download button), retry a failed statement with one click, and rebuild the database from the PDFs if it's ever lost. |
| **Trade-off** | Your statements sit on disk, privately (git-ignored). `forget` deletes them. |
| **Revisit when** | You'd rather not keep them. That's a small setting to add. |

---

## 5. Algorithms

### 5.1 The math check: replay every row and resync after a mismatch
| | |
|---|---|
| **Chose** | Start from the opening balance, apply each row, and compare with the bank's printed balance **after every row**. On a mismatch, report it, then continue from the bank's balance. |
| **Over** | Only comparing the final closing balance · stopping at the first error · continuing from our own (wrong) total |
| **Why** | Row-by-row checking points at the **exact row** ("Row 3: expected 945.80, statement shows 963.80"). Without resyncing, one misread would make *every* later row look wrong and hide the real culprit. A closing-balance check alone says "something is wrong somewhere". It's the free answer key every statement already prints. |
| **Trade-off** | Statements without running balances only get the closing check. Ones with no balances at all can't be verified, so every row goes to review (scenario S19). |
| **Revisit when** | Never. This is the heart of "the numbers are proven, not hoped". |

### 5.2 Credit cards: the balance goes *up* when you spend
| | |
|---|---|
| **Chose** | For card statements, the check flips the direction: spending adds to the balance (what you owe), payments reduce it |
| **Over** | Treating cards like bank accounts |
| **Why** | That's how card statements work. Without the flip, every card statement would fail the check. The AI reports the statement type (`kind`), and scenario S06 tests a full card statement. |
| **Trade-off** | Relies on the AI identifying the statement type correctly. If it doesn't, the check fails loudly rather than silently. |
| **Revisit when** | Never. |

### 5.3 Working out a missing opening balance
| | |
|---|---|
| **Chose** | If no opening balance is printed, calculate it from row 1: opening = row 1's balance − row 1's movement |
| **Over** | Refusing to check |
| **Why** | Some banks only print running balances. The first row's balance is enough to anchor every check that follows (scenario S17). |
| **Trade-off** | Row 1 itself is only checked indirectly (through the closing balance). |
| **Revisit when** | Never. |

### 5.4 Date check: valid and within the period (±7 days)
| | |
|---|---|
| **Chose** | Every date must be a real date inside the statement period, with 7 days of slack either side |
| **Over** | No date checks (the original design) · exact period boundaries |
| **Why** | Balances can't reveal a misread **date**, so a wrong year would silently file a row in the wrong month. The tests exposed this gap (scenarios S25, S26). Card statements often include purchases made a few days before the period starts, which is what the slack allows for. |
| **Trade-off** | A misread within the period (5 Nov read as 6 Nov) isn't caught. Harmless, since it stays in the same month nearly always. |
| **Revisit when** | Never. |

### 5.5 Reading 3 pages at a time, halving on overflow
| | |
|---|---|
| **Chose** | Send groups of 3 pages. If an answer is cut off, split the group in half and retry, down to single pages. |
| **Over** | The whole PDF in one request · one page per request · fixed smaller groups |
| **Why** | Whole-PDF answers for long statements can exceed the answer length limit. Page-by-page means more requests and repeats the instructions each time (cost). 3 pages is a sweet spot for typical statements. Halving adapts automatically to unusually dense pages with no tuning (scenario S03), and a single page that still can't fit fails clearly instead of guessing (S30). |
| **Trade-off** | A row split across a page boundary would be read in two halves. Statements almost never split a row across pages. |
| **Revisit when** | Statements routinely run to 100+ pages. Then read groups in parallel. |

### 5.6 Stitching page groups back together
| | |
|---|---|
| **Chose** | Header details (bank, account, period, opening balance) from the first group that has them; the closing balance from the last group that has it; transactions in order |
| **Over** | Asking the AI to merge |
| **Why** | Deterministic, free and testable. Page 1 has the header, the last page has the closing balance. |
| **Trade-off** | None. |
| **Revisit when** | Never. |

### 5.7 Shop names for rules: letters only, first three words
| | |
|---|---|
| **Chose** | `"AMZN Mktp US*2K4L95 Seattle WA"` → `"amzn mktp us"` |
| **Over** | The full description · fuzzy text matching · AI embeddings (meaning-based matching) |
| **Why** | Descriptions carry changing reference numbers. Stripping digits and keeping the first three words makes next month's `"AMZN Mktp US*9QX71"` match the same rule, simply, predictably and instantly. Fuzzy or meaning-based matching can match the wrong shop *confidently*, and needs tuning or AI calls. |
| **Trade-off** | Two different shops sharing their first three words would share a rule. Fixable by correcting one row. |
| **Revisit when** | You see repeated wrong matches. |

### 5.8 Keyword rules: whole words, first match wins
| | |
|---|---|
| **Chose** | `\bword\b` matching (whole words only, any capitalization), checked top to bottom in config.yaml |
| **Over** | Substring matching · scoring every category |
| **Why** | Substrings misfire ("sip" inside "gossip", "mart" inside "smart"). Whole-word matching is tested. "First match wins" in the order you wrote is easy to reason about: put more specific keywords higher. |
| **Trade-off** | Keywords must be whole words. |
| **Revisit when** | Never. |

### 5.9 Categorization order: your rules → saved rules → keywords → AI
| | |
|---|---|
| **Chose** | Saved merchant rules first (yours always beat the AI's), then keywords, and only then Claude |
| **Over** | Sending every row to the AI · keywords before saved rules |
| **Why** | **Cheaper** (known shops cost nothing: month 2 needed zero AI calls in the tests), **faster**, and **consistent** (the same shop always lands in the same category). Saved rules come before keywords because they're specific to one shop, while keywords are broad. |
| **Trade-off** | A wrong rule repeats its mistake, until you correct it once. |
| **Revisit when** | Never. |

### 5.10 Learn only from confident AI answers
| | |
|---|---|
| **Chose** | An AI answer becomes a saved rule only when its confidence is **high**. Your corrections always become rules (if "remember" is ticked). |
| **Over** | Learning from every AI answer |
| **Why** | Learning from unsure answers would lock in guesses, repeating them forever without review. Unsure rows go to review instead. Once you decide, your rule is saved. |
| **Trade-off** | Shops the AI is always unsure about keep costing an AI call until you review them once. |
| **Revisit when** | Never. |

### 5.11 Confidence as three words, not a percentage
| | |
|---|---|
| **Chose** | high, medium or low |
| **Over** | A probability ("87% sure") |
| **Why** | AI models' self-reported percentages are poorly calibrated: "87%" doesn't mean right 87% of the time. Three plain levels are more honest and map directly to a decision (review or not). |
| **Trade-off** | Coarser. |
| **Revisit when** | We measure calibration on your labeled data and find a finer scale useful. |

### 5.12 Categorizing about 100 rows per request, with short row numbers
| | |
|---|---|
| **Chose** | Batches of up to 100 rows. Each row gets a number 1–100 that Claude echoes back, instead of our 16-character IDs. |
| **Over** | One request per row · echoing our long IDs |
| **Why** | The instructions are sent once per 100 rows, not 100 times (cost and speed). Short numbers can't be mistyped. A row the AI skips isn't lost: it becomes "Other, low confidence" and goes to review. |
| **Trade-off** | A huge batch could hit the answer length limit. 100 keeps well within it (configurable). |
| **Revisit when** | Never. |

### 5.13 Your recent corrections are shown to the AI
| | |
|---|---|
| **Chose** | Include your last 40 corrections ("PIZZA PALACE DELIVERY" → Grocery) as examples in the instructions |
| **Over** | Ignoring them · fine-tuning a model |
| **Why** | The AI then applies *your* judgement to similar shops it hasn't seen ("PIZZA HUT DELIVERY"). Fine-tuning is expensive, slow and overkill. Forty examples cost a fraction of a cent. |
| **Trade-off** | Slightly longer requests. |
| **Revisit when** | Never. |

### 5.14 Spotting monthly charges
| | |
|---|---|
| **Chose** | A shop counts as a "monthly charge" if it's in a spending category, charged **3+ times**, the last two gaps are **26–35 days**, and the two charges before the latest are **within 10%** of each other (the latest may differ, which is how a price rise shows up) |
| **Over** | Any shop seen every month · asking the AI |
| **Why** | 26–35 days allows for months of different lengths and weekends. Three charges is the minimum to see a pattern. The amount check separates real subscriptions (29.99, 29.99, 29.99) from everyday shops you happen to visit monthly (fuel: 41, 58, 47). Excluding Savings and Investments stops "transfer to savings" looking like a subscription. These rules came from a test run that initially flagged rent, fuel and savings. |
| **Trade-off** | Yearly or weekly subscriptions aren't detected. |
| **Revisit when** | You have yearly subscriptions to catch. Add a 360–370-day rule. |

### 5.15 Alert rules and their thresholds
Every rule is tested just above and just below its threshold ([TESTING §8](TESTING.md#8-how-the-alert-rules-are-tested)).

| Alert | Rule | Why this threshold |
|---|---|---|
| **Double charge** | Same shop, same amount, within **2 days** | Card systems sometimes post a duplicate a day later. Beyond 2 days it's more likely a genuine repeat purchase. |
| **Unusually big charge** | More than **3×** the median of at least **3** earlier charges at that shop | The median ignores one-off outliers in history. 3× catches "412 at the supermarket" without flagging a bigger-than-usual shop. 3 earlier charges are needed before "usual" means anything. One alert per shop per day. |
| **Big first charge** | A shop's first-ever charge of **≥ 200** (configurable `large_charge`), spending only | New merchants charging a lot is the classic fraud and mistake pattern. 200 avoids noise from small new cafés. Transfers to savings and investments are excluded. |
| **Free trial turned paid** | A charge **≤ 1.00**, then a real charge from the same shop **7–30 days** later | Trials typically verify the card with 0–1 and convert after 7, 14 or 30 days. |
| **Subscription price increase** | A monthly charge's latest amount is **> 2%** above the previous | Ignores rounding and currency wobble, and catches real price rises (12.99 → 15.99). |
| **Forgotten subscription** | A monthly charge ([5.14](#514-spotting-monthly-charges)) **≤ 200** that **isn't** filed as Subscriptions | Known subscriptions need no alert. Big monthly payments (rent, loans) aren't the forgotten kind. |
| **Category spike** | This month's category total is **> 1.5×** its average over the previous **3 months** (all 3 must have data) | 1.5× is a meaningful jump. 3 months of history smooths out one-offs, and requiring all 3 prevents alarms in your first months. |

### 5.16 Wait until a dropped file stops growing
| | |
|---|---|
| **Chose** | Before processing an inbox file, wait until its size is unchanged for **3 checks, 1 second apart** |
| **Over** | Processing as soon as the file appears |
| **Why** | Browsers and Mail write files gradually. Processing a half-written PDF would fail (and look like a broken file). Three stable checks is a simple, reliable signal (tested). |
| **Trade-off** | About 3 seconds of delay. |
| **Revisit when** | Never. |

### 5.17 Sheet tabs named `YYYY-MM`, newest first, totals as formulas
| | |
|---|---|
| **Chose** | Tab names like `2026-11`. Order: Summary, then newest month first. Summary totals are **formulas** (`=SUM('2026-11'!D2:D)`). Empty tabs are deleted. Values are written "as if typed" (`USER_ENTERED`). |
| **Over** | Names like "Nov 2026" · oldest first · totals written as plain numbers |
| **Why** | `YYYY-MM` sorts correctly and can't be misread. Newest first is what you open the sheet for. Formulas keep the Summary correct even if you inspect or sort a tab, and anyone can click a total to see where it comes from. Deleting emptied tabs avoids clutter after corrections. "As typed" makes Google treat dates as dates and amounts as numbers, so your own formulas work on them. |
| **Trade-off** | Formulas reference tab names, so renaming a tab by hand breaks its total (another reason the sheets are read-only). |
| **Revisit when** | Never. |

---

## 6. Security and privacy

### 6.1 Secrets and data are git-ignored before the first commit
| | |
|---|---|
| **Chose** | `.gitignore` covers `.env`, `service_account.json`, `config.yaml`, `/data/`, `*.pdf` and `demo/` from the very first commit. The only PDFs allowed are the fake test fixtures. |
| **Over** | Remembering to be careful |
| **Why** | Accidentally committed secrets and statements are the most common real-world leak, and git history keeps them forever. The setup checklist also verifies `.gitignore`. |
| **Trade-off** | New contributors copy `config.example.yaml` and `.env.example`. |
| **Revisit when** | Never. |

### 6.2 Only the last 4 digits are stored
| | |
|---|---|
| **Chose** | The AI is told to return only the last 4 digits of account and card numbers. That's all the database and sheets ever hold. |
| **Over** | Storing full numbers |
| **Why** | Four digits are enough to tell accounts apart. A database without full numbers is far less valuable if it ever leaks. |
| **Trade-off** | None. |
| **Revisit when** | Never. |

### 6.3 PDFs are unlocked on your laptop
| | |
|---|---|
| **Chose** | Decrypt locally with pypdf, then send unlocked page groups |
| **Over** | Sending the locked PDF together with its password |
| **Why** | Your statement password (often your date of birth or ID number) never leaves your computer. |
| **Trade-off** | None. |
| **Revisit when** | Never. |

### 6.4 v1 sends whole pages to Claude
| | |
|---|---|
| **Chose** | Pages go to Claude as they are, including your name and address in the header |
| **Over** | Removing personal details first ("privacy mode") |
| **Why** | Redacting reliably requires understanding the layout, which is the hard problem Claude solves for us. A clumsy redaction could also remove transaction text. Pages travel over an encrypted connection to the API. This is an honest trade-off, stated in the README and Architecture docs. |
| **Trade-off** | Your name, address and account number (in the header) are seen by the AI provider. Check Anthropic's data-handling terms for API usage. |
| **Revisit when** | Privacy mode (Plan → Phase 7): extract text locally, blank out names and numbers, send text only. |

### 6.5 The web app only listens to your own computer
| | |
|---|---|
| **Chose** | Always start Streamlit with `--server.address localhost` |
| **Over** | Default network settings |
| **Why** | Otherwise anyone on the same Wi-Fi (a café, an office) could open your finances in their browser. |
| **Trade-off** | You can't open it from your phone. |
| **Revisit when** | You host it at home behind a login. |

### 6.6 Logs contain IDs and counts, not money
| | |
|---|---|
| **Chose** | Log statement IDs, row counts, statuses and error types. Never descriptions, amounts or account numbers. |
| **Over** | Logging everything for easy debugging |
| **Why** | Logs get pasted into chats and bug reports. They should be boring. |
| **Trade-off** | Debugging sometimes needs the database itself. |
| **Revisit when** | Never. |

### 6.7 Spend limit on the Claude account
| | |
|---|---|
| **Chose** | The setup guide recommends a monthly spend limit (e.g. $5) in the Claude Console |
| **Over** | No limit |
| **Why** | A bug, such as a loop re-processing files, can never become an expensive surprise. |
| **Trade-off** | Hitting the limit pauses processing until next month (or until you raise it). |
| **Revisit when** | Never. |

---

## 7. Reliability and error handling

### 7.1 Fail safe: nothing half-finished reaches Google Sheets
| | |
|---|---|
| **Chose** | Only verified, reviewed rows are eligible for sync. A failed sync marks nothing as synced. |
| **Over** | "Best effort" partial updates |
| **Why** | Your sheets should only ever show numbers you can trust. Every statement scenario test checks this rule. |
| **Trade-off** | Sometimes data waits for you. |
| **Revisit when** | Never. |

### 7.2 Everything is safe to retry
| | |
|---|---|
| **Chose** | Re-processing, re-syncing and re-uploading are all designed to give the same result |
| **Over** | Operations that must only ever run once |
| **Why** | Networks fail, laptops sleep, APIs get busy. When "just run it again" is always the answer, users (and automation) never have to work out what state things are in. Fingerprints, `INSERT OR IGNORE`, tab rebuilds and "categorize everything still pending" make this true, and tests prove it. |
| **Trade-off** | Retrying a failed statement re-reads it (a few cents). |
| **Revisit when** | Never. |

### 7.3 Plain-English error messages
| | |
|---|---|
| **Chose** | Every expected failure becomes a sentence that says what to do: "This PDF is locked. Enter its password…", "Can't open the Travel spreadsheet. Share it with robot@… as Editor." |
| **Over** | Showing technical errors |
| **Why** | The user may not be technical. A message that says *what to do* turns a dead end into a 30-second fix. Unexpected errors still say where details are logged. |
| **Trade-off** | More code mapping errors to messages. |
| **Revisit when** | Never. |

### 7.4 Alerts can never fail a statement
| | |
|---|---|
| **Chose** | If the alert scan has a problem, it's logged and processing continues |
| **Over** | Letting any error stop processing |
| **Why** | Alerts are a bonus. A test showed an impossible date crashing the alert scan, which turned a correctly held statement into a failure. Core results must not depend on optional features. |
| **Trade-off** | A broken alert rule could go unnoticed (it's logged). |
| **Revisit when** | Never. |

### 7.5 Automatic backups before risky operations
| | |
|---|---|
| **Chose** | Back up the database before every sync and every upgrade, keeping the newest 10 copies |
| **Over** | Manual backups only |
| **Why** | Cheap insurance (a copy takes milliseconds). Upgrades and syncs are where a bug could do the most damage. |
| **Trade-off** | A little disk space. |
| **Revisit when** | Never. Also copy `data/backups/` off the laptop occasionally. |

---

## 8. User experience

### 8.1 "Doesn't add up" and "AI wasn't sure" are handled in different places
| | |
|---|---|
| **Chose** | The Review page only shows rows the AI was unsure about. Statements that don't add up are handled on the Statements page, with the exact problem and a PDF download. |
| **Over** | One mixed review list |
| **Why** | They're different tasks. "Is this the right category?" is a quick click. "Does row 37 match the PDF?" needs the PDF open. Mixing them would invite approving numbers without checking. |
| **Trade-off** | Two places to look. The sidebar shows both counts. |
| **Revisit when** | Never. |

### 8.2 Sync is a button; auto-sync is opt-in
| | |
|---|---|
| **Chose** | A sidebar "Sync to Google Sheets" button. `auto_sync: true` in settings for automation. |
| **Over** | Syncing automatically after every change |
| **Why** | You stay in control of when your shared sheets change, such as after finishing a review session. For hands-off use, auto-sync is one setting away. |
| **Trade-off** | One extra click. |
| **Revisit when** | You always want auto-sync. Turn it on. |

### 8.3 "Remember my choice" is ticked by default
| | |
|---|---|
| **Chose** | Corrections become rules unless you untick the box |
| **Over** | Opt-in remembering |
| **Why** | Most corrections apply to the shop in general ("this is always groceries"), and remembering is what makes the review queue shrink each month. |
| **Trade-off** | A one-off exception needs the box unticked. |
| **Revisit when** | Never. |

### 8.4 A no-keys demo
| | |
|---|---|
| **Chose** | `python scripts/demo.py` builds 3 months of fake statements, processed by a pretend Claude |
| **Over** | Requiring setup before anyone can see the app |
| **Why** | You can explore every page, alert and chart in a minute, before spending 30 minutes on keys and Google Cloud. |
| **Trade-off** | Demo data isn't your data. |
| **Revisit when** | Never. |

---

## 9. Testing

### 9.1 Fakes that behave like the real thing, not mocks
| | |
|---|---|
| **Chose** | Small working imitations: a fake Google that enforces grid sizes and evaluates formulas, AI stand-ins that genuinely read PDF text, an in-memory Keychain |
| **Over** | "Mocks" that only check a function was called · testing against the real services |
| **Why** | Fakes test *behaviour* (does the Summary total equal the database total?), not wiring, so they catch real bugs and survive refactoring. Real services in automated tests would cost money, need your passwords, change your real sheets and give different answers on different days. Full explanation: [TESTING.md](TESTING.md). |
| **Trade-off** | A fake can drift from the real service. Live tests and `cli.py check` cover the real services. |
| **Revisit when** | Never. |

### 9.2 Generated fake statements, never real ones
| | |
|---|---|
| **Chose** | Statements are drawn by code (reportlab), so every test knows the exact truth |
| **Over** | Anonymized real statements |
| **Why** | Zero privacy risk. Each test knows the *exact* expected values, and creating a new situation (a 320-row month, a card statement, accented names) takes one line. |
| **Trade-off** | Real bank layouts are messier. The math check and live tests cover that gap. |
| **Revisit when** | Never. |

### 9.3 Thresholds tested on both sides
| | |
|---|---|
| **Chose** | Every alert rule is tested just above and just below its limit (199.99 vs 200, 6 vs 7 days…) |
| **Over** | One "happy path" test per rule |
| **Why** | Off-by-one mistakes (`>` vs `>=`) live exactly at the boundary. |
| **Trade-off** | More tests (they take milliseconds). |
| **Revisit when** | Never. |

### 9.4 Live AI tests are opt-in
| | |
|---|---|
| **Chose** | `pytest -m live` sends the fixtures to the real Claude, and is skipped without a key |
| **Over** | Calling the real AI on every test run · never testing the real AI |
| **Why** | Every run of the normal suite stays free, fast and repeatable, and the real model can still be checked on demand (after setup, or after changing the instructions). |
| **Trade-off** | Someone has to remember to run them. |
| **Revisit when** | We add CI (automatic tests on every change). Then run live tests nightly. |

---

## 10. Cost

### 10.1 Pay for AI only where it adds value
| | |
|---|---|
| **Chose** | Free steps first (fingerprints, saved rules, keywords), AI only for what's left, in batches, with every call's cost logged |
| **Over** | AI for everything |
| **Why** | Re-uploads cost nothing, known shops cost nothing, and instructions are sent once per 100 rows. The cost log (`python cli.py costs`) makes spending visible instead of guessed. A typical month costs well under $1. |
| **Trade-off** | Some extra code. |
| **Revisit when** | Never. |

### 10.2 The most capable model by default, cheaper only when measured
| | |
|---|---|
| **Chose** | Default to Claude Opus 5.5, and use `scripts/eval_categories.py` to test cheaper models on *your* labeled transactions before switching |
| **Over** | Starting with the cheapest model |
| **Why** | Accuracy matters more than cents here, and "a cheaper model is probably fine" should be measured, not assumed. The eval reports accuracy, mix-ups and the cost of the run. |
| **Trade-off** | Slightly higher cost until you measure. |
| **Revisit when** | The eval shows a cheaper model at ≥ 95% on your data. |

---

## 11. Deliberately postponed

> 💡 Good ideas we said "not yet" to, and the trigger that would make us build them.

| Idea | Why not yet | Build it when |
|---|---|---|
| **Fetch statements from Gmail** | Needs Google OAuth for your mailbox and per-bank email rules. A Mail rule saving PDFs into the inbox folder does the job. | You get statements by email from several banks and want zero clicks |
| **Privacy mode** (remove name and numbers before the AI) | Hard to do reliably on unknown layouts ([6.4](#64-v1-sends-whole-pages-to-claude)) | Sending headers to the AI provider is unacceptable to you |
| **Local fast-path reader** (pdfplumber, no AI) | Only worth it for one dominant bank, and the AI already works for all | One bank is ≥ 80% of your statements and you want it free |
| **Multiple currencies** | Needs a rate source and rules ([1.12](#112-no-currency-conversion)) | You add a foreign-currency account |
| **Budgets with warnings** | Tracking first, budgeting second | You've got 3+ months of history and want targets |
| **Questions in plain English** ("travel in Q3?") | A nice extra on top of a working ledger | The ledger is the stable foundation it needs (it is now) |
| **PostgreSQL / multiple users** | One person doesn't need a server ([3.6](#36-sqlite-for-the-database)) | Two people need to use it at the same time |
| **A small web API (FastAPI)** | Only needed for phone shortcuts or other apps | You want to upload from your phone |
| **Integer-cent money storage** | Rounding is exact for add/subtract-only data ([4.2](#42-money-as-rounded-decimals-compared-with-a-1-cent-tolerance)) | We add conversion or interest calculations |
| **Yearly and weekly subscription detection** | Monthly covers most subscriptions | You have yearly subscriptions you keep forgetting |
