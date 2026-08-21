# CASINO ROYALS — Hosting Guide

Two files. One folder. One wallet.

| File | What it is |
|---|---|
| `casino_bot.py` | The Telegram bot (old 6 PVP games + wallet + `/miniapp` button) |
| `miniapp.py` | The Mini App web server (14 table games, green & gold UI baked inside) |
| `requirements.txt` | Python packages needed |

Both files share ONE SQLite database — deposit in the bot, play in the Mini
App, withdraw in the bot. Same balance everywhere.

---

## WHERE TO HOST

1. **Your bot hosting panel (hoster bot)** — easiest for you. Upload the two
   `.py` files in the SAME folder. Run `casino_bot.py` as the bot,
   `miniapp.py` as a web app on port **8000**.
2. **Railway** — alternative if the panel can't run FastAPI. The
   `Dockerfile` in this package builds everything automatically; full
   walkthrough in `extras/FULL_GUIDE.md` section 5.
3. **VPS** — cheapest long-term for Indian users (Hostinger Mumbai ~₹400/mo).
   See `extras/FULL_GUIDE.md` section 6.

---

## HOW TO HOST (hoster bot panel)

### Step 1 — Put your bot token in casino_bot.py

Open `casino_bot.py` in a text editor (Notepad works). Near the top you see:

```python
HARDCODED_BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"
```

Replace the placeholder with your real token from @BotFather:

```python
HARDCODED_BOT_TOKEN = "8307026945:AA...your-real-token"
```

### Step 2 — Upload to the panel

- Upload `casino_bot.py`, `miniapp.py` and `requirements.txt` into the **same
  folder** (same directory — this is important, they must see each other).
- Panel Python version: **3.9 or newer**.
- Make sure these packages are installed (most panels auto-install from
  requirements.txt; if the panel has no auto-install, install them yourself):

  ```
  python-telegram-bot==22.7  Pillow  aiohttp  Telethon  cryptography  fastapi  uvicorn
  ```

### Step 3 — Start both processes

- Start `casino_bot.py` as the **Bot** process (no port).
- Start `miniapp.py` as the **Web** process with **port 8000**.

### Step 4 — Get the Mini App URL and paste it

Your panel will show a public URL for miniapp.py (something like
`https://yourhost.example/miniapp` — must be **HTTPS**).

Open `casino_bot.py` again, scroll to the BOTTOM section, and find:

```python
HARDCODED_MINIAPP_URL = "PASTE_YOUR_MINIAPP_URL_HERE"
```

Paste your URL there, save, restart the bot. Until you do this, `/miniapp`
prints instructions instead of a broken button.

### Step 5 — Connect the button in Telegram

BotFather → `/mybots` → your bot → **Bot Settings → Menu Button**
→ URL: your Mini App URL, text: `Casino Royals`.

Done. The menu button next to the message box opens the casino inside
Telegram.

---

## RAILWAY QUICK START (exact steps)

1. GitHub repo -> Railway -> new service (Dockerfile at root is auto-detected).
2. **Settings -> Build -> Builder -> Dockerfile** (not Railpack).
3. **Settings -> Volumes -> Add Volume -> mount path `/data`**
   (mobile app hides Volumes - use a browser, or CLI:
   `railway volume add --mount-path /data`)
4. **Variables:** `TELEGRAM_BOT_TOKEN`, `BOT_ADMIN_IDS` (your Telegram id).
5. **Settings -> Networking -> Public Networking -> Generate Domain**
   -> that HTTPS URL is your Mini App link (paste in BotFather Menu Button).
6. Do NOT enable "Serverless" (the bot would sleep). Healthcheck: `/api/config`.

The Dockerfile must NOT contain a `VOLUME` line - Railway rejects it.

---

## MOVING YOUR OLD DATABASE (IMPORTANT)Balances live in the database file. Never run old bot + new bot at the same
time — stop the old one first.

**Easy way (recommended):**
1. On the OLD bot (still running): send `/backup` to it privately → you get
   an encrypted `.crbackup` file.
2. Stop the old bot.
3. On the NEW bot: reply to that `.crbackup` file with `/bupload` → confirm
   the restore → maintenance mode turns ON → test `/balance` → `/maintenance off`.

**Direct way (if panel has a file manager):**
Copy the old database file (default name `group_dice_royale.db`) into the
same folder as the two `.py` files, keep the same filename, start the bot.

⚠️ Ask your panel: do files survive restarts? If the panel wipes files on
restart, your balances will be lost — use a panel with persistent storage,
and save a `/backup` file regularly.

---

## AFTER IT'S RUNNING

- `/balance` in the bot = same balance as the Mini App header.
- `/admin` = panel; all old commands work exactly as before.
- `/miniapp` = button to open the Mini App from any chat.

## NOTES

- `miniapp.py` is standalone — the UI is baked inside it. The
  `extras/static/index.html` + `extras/bake_index.py` are only for changing
  the UI later (`python bake_index.py` regenerates the embedded copy).
- Tests: `extras/test_bot.py` and `extras/test_miniapp.py` (both passing).
- Full detail (Railway/VPS/SSL/troubleshooting): `extras/FULL_GUIDE.md`.
