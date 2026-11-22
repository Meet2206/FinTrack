# 🧠 Prompts

[Readme](../Readme.md) · [Plan](../Plan.md) · [Architecture](../Architecture.md) · [Backend](../Backend.md) · [DB](../DB.md) · [Testing](../TESTING.md) · [Reason](../Reason.md) · **Prompts**

| File | What it's for |
|---|---|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | **The handoff.** Everything an AI assistant needs to continue this project on any computer: what it is, where it's up to, how it works, the rules, the commands, the gotchas, what's next. |
| [app/extract-statement.md](app/extract-statement.md) | 🟢 Live: the instructions Claude follows to **read** a statement |
| [app/categorize-transactions.md](app/categorize-transactions.md) | 🟢 Live: the instructions Claude follows to **sort** transactions into categories |

> 💡 **"Live"** means the app reads that file when it starts. Edit the text between its markers and you've changed what Claude is told. Each file explains how to do that safely.

---

## Moving to another laptop

### 1. Move the code

Pick one:

- **GitHub (recommended):** push this folder to a **private** repository, then `git clone` it on the new laptop. You get the full history, and both laptops stay in sync afterwards.
- **Copy the folder:** zip it, or use AirDrop or USB. Leave out `.venv/` and `__pycache__/`: they only work on the machine that made them and are rebuilt in step 3. The hidden `.git/` folder comes along, so the history does too.

> On the new laptop, name the folder without spaces (e.g. `meet-project`). The original folder name ends in a space, which trips up some commands.

### 2. Move your private files (only once they exist)

These are deliberately **not** in git, so step 1 doesn't carry them. Today none of them exist yet, so skip this until you've set the app up for real.

| File | What it is | If you lose it |
|---|---|---|
| `.env` | Your Claude API key | Create a new key at platform.claude.com |
| `config.yaml` | Your Google Sheet IDs and settings | Copy `config.example.yaml` and fill it in again |
| `service_account.json` | The Google robot account's key | Create a new key in Google Cloud |
| `data/` | **Your database** (`ledger.db`), stored statements and backups | ⚠️ This is the master record. The sheets can be rebuilt from it, but not the other way round. **Don't lose it.** |

Copy them with a USB stick, AirDrop or a password manager. **Never** send them by email or chat, and never commit them.

Saved PDF passwords live in the old laptop's keychain and don't move. Add them again with `python cli.py password add <name>`.

### 3. Set up the new laptop

```bash
cd meet-project
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest                   # 210 tests, no keys needed. Should all pass.
python cli.py check                # what's still missing for real use
```

### 4. Give the AI the context

- **Claude Code** (terminal or VS Code): nothing to do. [CLAUDE.md](../CLAUDE.md) in the project folder loads `PROJECT_CONTEXT.md` automatically at the start of every session. Start with something like *"Read the project context, run the tests, and tell me where we are."*
- **Any other AI assistant** (claude.ai, Cursor, ChatGPT…): open [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), copy **all** of it, and paste it as your first message. Then say what you want to do next.

### 5. Keep the handoff fresh

`PROJECT_CONTEXT.md` tells the AI to update it whenever the project changes. Check its "Current state" and "Open items" sections now and then. A handoff that's out of date is worse than none.
