# daily-digest

Three Telegram digests delivered every morning (Europe/Berlin):

| Time  | Digest | Sources |
|-------|--------|---------|
| 08:00 | Tech & ML | Hacker News + `r/MachineLearning`, `r/technology`, `r/CryptoCurrency` |
| 08:05 | Memes | `r/memes`, `r/dankmemes` |
| 08:10 | World News | Tagesschau RSS, Handelsblatt RSS |

No auth anywhere. No Docker. No database. One Python package, three systemd timers, one Telegram bot token.

## Requirements

- Python 3.11+
- Telegram bot token + chat ID (create via `@BotFather`, then send the bot a message and read `chat_id` from `getUpdates`)
- For Reddit: a descriptive `User-Agent` string (Reddit throttles generic UAs to 429)

## Local dev

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env   # fill in values
set -a; source .env; set +a

.venv/bin/python -m daily_digest tech  --dry-run
.venv/bin/python -m daily_digest memes --dry-run
.venv/bin/python -m daily_digest news  --dry-run
```

`--dry-run` prints the MarkdownV2 payload to stdout instead of sending it.

Send for real (requires `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`):

```bash
.venv/bin/python -m daily_digest tech
```

## Deploy to Hetzner VM

One-time bootstrap, as root:

```bash
apt update && apt install -y python3 python3-venv git

# System account for the daemon. No -m (skel files would make the home dir
# non-empty and break `git clone` below). Create the home dir ourselves,
# empty and owned by digest, then clone into it.
useradd -r -s /bin/bash -d /opt/daily-digest digest
install -d -m 0755 -o digest -g digest /opt/daily-digest
sudo -u digest git clone <repo-url> /opt/daily-digest

cd /opt/daily-digest
sudo -u digest python3 -m venv .venv
sudo -u digest .venv/bin/pip install -e .

install -d -m 0700 -o digest -g digest /etc/daily-digest
cat >/etc/daily-digest/env <<'EOF'
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
REDDIT_USER_AGENT=daily-digest/0.1 (by /u/yourname)
EOF
chmod 0600 /etc/daily-digest/env
chown digest:digest /etc/daily-digest/env

bash deploy/install.sh
```

`deploy/install.sh` copies the unit files to `/etc/systemd/system/`, runs `daemon-reload`, then `enable --now` on all three timers. It prints the next fire times via `systemctl list-timers`.

### Updates

```bash
cd /opt/daily-digest
sudo -u digest git pull
sudo -u digest .venv/bin/pip install -e .
```

Timers re-launch a fresh Python process on each fire, so no service restart is needed.

### Inspect

```bash
systemctl list-timers 'daily-digest-*.timer'
journalctl -u 'daily-digest@*.service' -n 100 --no-pager
sudo systemctl start daily-digest@tech.service   # fire manually
```

## Layout

```
src/daily_digest/
├── __main__.py         # CLI: python -m daily_digest {tech,memes,news} [--dry-run]
├── config.py           # env vars + source lists
├── format.py           # MarkdownV2 render
├── telegram.py         # Bot API sender (4096-char chunking)
└── sources/
    ├── hackernews.py   # Firebase REST, unauth
    ├── reddit.py       # .json endpoints, unauth, UA required
    └── rss.py          # feedparser wrapper
deploy/
├── daily-digest@.service        # templated oneshot, %i = digest name
├── daily-digest-tech.timer      # 08:00 Europe/Berlin
├── daily-digest-memes.timer     # 08:05 Europe/Berlin
├── daily-digest-news.timer      # 08:10 Europe/Berlin
└── install.sh
```

## Notes

- **DST is handled by systemd** via `OnCalendar=... Europe/Berlin`. No hardcoded UTC offsets.
- **Fault tolerance:** `asyncio.gather(..., return_exceptions=True)` means one failing source (e.g. Reddit 429) does not block the other sources — failed ones are logged and skipped.
- **No dedupe across days** in v1. If a story trends two days in a row you will see it twice. Add a SQLite `seen(url, date)` table later if this becomes annoying.
- **Reddit 429 fallback:** if the unauth `.json` endpoints start rate-limiting, register a free "script" OAuth app (client id + secret only, no user token flow) and add the token to the `User-Agent`/bearer.
