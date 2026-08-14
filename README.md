# daily-digest

Two Telegram digests delivered every morning (Europe/Berlin), plus an hourly Fear & Greed watch:

| Time  | Digest | Sources |
|-------|--------|---------|
| 08:00 | Tech & ML | Hacker News, top 10 |
| 08:10 | World News | Tagesschau RSS, Handelsblatt RSS, plus a Fear & Greed section |
| hourly at :17 | Fear & Greed check | CNN (stocks), alternative.me (crypto) |

No auth anywhere. No Docker. One Python package, three systemd timers, one Telegram bot token, one SQLite file.

## Fear & Greed

Two indices, each 0-100: CNN's for US stocks, alternative.me's for crypto.

- The **08:10 news digest** always carries a section with both current values and how they compare to yesterday, a week ago and a month ago.
- The **hourly check** sends a separate Telegram alert the moment an index enters an extreme zone. Stocks are extreme at 20 or below and 80 or above; crypto is stricter, 10 and 90, because it parks in its extreme zones for weeks during a trend. Thresholds are `FEARGREED_EXTREMES` in `config.py`.
- **One alert per crossing.** An index that stays extreme stays quiet; it has to leave the zone and come back to alert again. The comparison is against the last reading in the database, so a restart does not re-alert.
- Every reading the hourly check takes is stored in SQLite (`DIGEST_DB_PATH`, default `/var/lib/daily-digest/feargreed.db` on the VM). The digest only reads the APIs, so it can never advance the state the alert logic compares against.

## Requirements

- Python 3.11+
- Telegram bot token + chat ID (create via `@BotFather`, then send the bot a message and read `chat_id` from `getUpdates`)

## Local dev

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env   # fill in values
set -a; source .env; set +a

.venv/bin/python -m daily_digest tech      --dry-run
.venv/bin/python -m daily_digest news      --dry-run
.venv/bin/python -m daily_digest feargreed --dry-run
```

`--dry-run` prints the MarkdownV2 payload to stdout instead of sending it. For `feargreed` it prints the current readings plus any alert that would have gone out, reads the database to work out whether this is a crossing, and writes nothing.

Send for real (requires `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`):

```bash
.venv/bin/python -m daily_digest tech
```

Tests (stdlib `unittest`, no network, no extra dependencies):

```bash
.venv/bin/python -m unittest discover
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
EOF
chmod 0600 /etc/daily-digest/env
chown digest:digest /etc/daily-digest/env

bash deploy/install.sh

# Optional, once: load the published history (CNN ~1 year, alternative.me
# back to 2018) so the database starts with context instead of empty.
sudo -u digest DIGEST_DB_PATH=/var/lib/daily-digest/feargreed.db \
  /opt/daily-digest/.venv/bin/python -m daily_digest feargreed --backfill
```

`deploy/install.sh` copies the unit files to `/etc/systemd/system/`, runs `daemon-reload`, then `enable --now` on every timer that is not already disabled on the host. It prints the next fire times via `systemctl list-timers`.

The service unit declares `StateDirectory=daily-digest`, so systemd creates `/var/lib/daily-digest` owned by the service user and keeps it writable despite `ProtectSystem=strict`. The backfill is idempotent, so re-running it costs two HTTP requests and stores only what is genuinely new.

### Updates

```bash
cd /opt/daily-digest
sudo -u digest git pull
sudo -u digest .venv/bin/pip install -e .
bash deploy/install.sh   # as root, whenever deploy/ changed in the pull
```

Timers re-launch a fresh Python process on each fire, so no service restart is needed. Unit files are the exception: they live in `/etc/systemd/system` and `git pull` does not touch them, so a release that adds a timer or edits the service needs `install.sh` re-run or the new timer silently never fires. It is idempotent, and it has to run after the `pip install`, not before.

### Inspect

```bash
systemctl list-timers 'daily-digest-*.timer'
journalctl -u 'daily-digest@*.service' -n 100 --no-pager
sudo systemctl start daily-digest@tech.service   # fire manually
```

## Layout

```
src/daily_digest/
├── __main__.py         # CLI: python -m daily_digest {tech,news,feargreed}
├── config.py           # env vars + source lists + Fear & Greed thresholds
├── feargreed.py        # Reading type, zone rules, alert decision (pure)
├── format.py           # MarkdownV2 render
├── store.py            # SQLite reading history
├── telegram.py         # Bot API sender (4096-char chunking)
└── sources/
    ├── feargreed.py    # CNN + alternative.me JSON, unauth
    ├── hackernews.py   # Firebase REST, unauth
    └── rss.py          # feedparser wrapper
tests/                  # stdlib unittest + saved API payloads
deploy/
├── daily-digest@.service          # templated oneshot, %i = command name
├── daily-digest-tech.timer        # 08:00 Europe/Berlin
├── daily-digest-news.timer        # 08:10 Europe/Berlin
├── daily-digest-feargreed.timer   # hourly at :17 Europe/Berlin
└── install.sh
```

## Notes

- **DST is handled by systemd** via `OnCalendar=... Europe/Berlin`. No hardcoded UTC offsets.
- **Fault tolerance:** `asyncio.gather(..., return_exceptions=True)` means one failing feed does not block the others — failed ones are logged and skipped. Tech has only Hacker News, so a failure there fails the run instead of sending an empty digest.
- **No dedupe across days** in v1. If a story trends two days in a row you will see it twice. Add a SQLite `seen(url, date)` table later if this becomes annoying.
- **The CNN endpoint is unofficial** and can disappear without notice. It answers `418 I'm a teapot. You're a bot.` unless the request carries both a browser `User-Agent` and a `cnn.com` `Referer`. If it starts failing, the news digest drops the stocks line and the hourly check alerts on crypto alone; the failure is logged, not raised.
- **An index oscillating across a threshold re-alerts on every crossing** (79, 81, 79, 81). Not seen in practice on daily data. If it happens, add a hysteresis band rather than widening the threshold.
