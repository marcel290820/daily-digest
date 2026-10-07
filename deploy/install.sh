#!/usr/bin/env bash
# Install daily-digest systemd units. Run as root on the Hetzner VM.
# Prereqs: /opt/daily-digest checked out, venv created, /etc/daily-digest/env populated.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "install.sh: must run as root" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST_DIR=/etc/systemd/system

# StateDirectory= in the unit only creates this when the service first runs,
# and the documented backfill runs before that, as the service user.
install -d -m 0755 -o digest -g digest /var/lib/daily-digest

# Capture operator-disabled timers before installing new units. A newly copied
# unit also reports disabled, which must not prevent its first activation.
disabled_timers=" "
for name in tech news feargreed system; do
  if [[ "$(systemctl is-enabled "daily-digest-$name.timer" 2>/dev/null)" == "disabled" ]]; then
    disabled_timers+="$name "
  fi
done

install -m 0644 "$SRC_DIR/daily-digest@.service"        "$DST_DIR/daily-digest@.service"
install -m 0644 "$SRC_DIR/daily-digest-tech.timer"      "$DST_DIR/daily-digest-tech.timer"
install -m 0644 "$SRC_DIR/daily-digest-news.timer"      "$DST_DIR/daily-digest-news.timer"
install -m 0644 "$SRC_DIR/daily-digest-feargreed.timer" "$DST_DIR/daily-digest-feargreed.timer"

install -m 0644 "$SRC_DIR/daily-digest-system.timer" "$DST_DIR/daily-digest-system.timer"

systemctl daemon-reload

# Enable what is new, leave alone what the operator switched off. Blindly
# enabling every timer re-arms a disabled digest, and `--now` on a Persistent
# timer whose last fire is in the past runs the missed job on the spot.
for name in tech news feargreed system; do
  unit="daily-digest-$name.timer"
  if [[ "$disabled_timers" == *" $name "* ]]; then
    echo "skipping $unit (disabled on this host)"
    continue
  fi
  systemctl enable --now "$unit"
done

echo
echo "Installed. Next fires:"
systemctl list-timers 'daily-digest-*.timer' --all --no-pager
