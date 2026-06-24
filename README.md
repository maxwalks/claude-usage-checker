# Claude Usage Monitor — Unicorn HAT HD

Glanceable Claude usage on a Raspberry Pi 5 + Pimoroni Unicorn HAT HD (16×16).
Shows your **5-hour session limit consumed** as a Ring gauge and an Equalizer,
auto-cycling every 10s. Renderers ported from the claude.ai/design project.

## Data source
Reads Claude Code's own usage endpoint (`/api/oauth/usage`) using the account
OAuth token in `~/.claude/.credentials.json`. It's account-wide, so the Pi shows
the same figure as your dev machine. The token is auto-refreshed when it expires,
so it runs unattended — just make sure `~/.claude/.credentials.json` exists on the
Pi (run `claude` and log in once, or copy the file over).

## Run

On the Pi (real hardware — `unicornhathd` already installed):
```bash
python3 monitor.py
```

On a desktop for development (simulator):
```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python monitor.py           # live data in a sim window
./venv/bin/python monitor.py --mock    # sweep 0→100, no network (check colors/edges)
python3 monitor.py --test              # assert-based self-checks
```

## Auto-start on boot (Pi)
`/etc/systemd/system/claude-usage.service`:
```ini
[Unit]
Description=Claude Usage Monitor
After=network-online.target

[Service]
User=pi
ExecStart=/usr/bin/python3 /home/pi/claude_usage_monitor/monitor.py
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now claude-usage
```

## Tuning
Constants at the top of `monitor.py`: `BRIGHTNESS`, `ROTATION` (set to match how the
HAT is mounted), `CYCLE_SECS`, `FETCH_SECS`. On fetch failure it holds the last value;
after 2+ consecutive failures it shows a red **X**.
