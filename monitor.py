#!/usr/bin/env python3
"""Claude usage monitor for the Unicorn HAT HD (16x16).

Shows the 5-hour session limit consumed as a Ring gauge / Equalizer, auto-cycling.
Data: Claude Code's own usage endpoint (account-wide, fetched over the network).
Renderers ported from the claude.ai/design "Unicorn Usage Monitor" project.
"""
import argparse
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request

# --- calibration knobs (hardware never matches paper) ---
BRIGHTNESS = 0.5          # ponytail: tune on the physical matrix
ROTATION = 0              # ponytail: depends on how the HAT is mounted
CYCLE_SECS = 10           # ring <-> equalizer
FETCH_SECS = 5
FPS = 30
EASE = 0.07               # display value easing toward target (from design)

N = 16
CREDS = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"  # ponytail: verify at impl
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"          # Claude Code OAuth client
USER_AGENT = "claude-cli/2.0.0 (external, cli)"             # some edges 403 a bare urllib UA


# ---------------- color + buffer helpers (ported from design draw()) ----------------
_STOPS = [(0.0, (46, 204, 150)), (0.5, (230, 196, 72)),
          (0.78, (240, 140, 46)), (1.0, (239, 68, 68))]


def _lerp(a, b, t):
    return a + (b - a) * t


def ramp(u):
    """green -> yellow -> orange -> red over u in [0,1]."""
    u = max(0.0, min(1.0, u))
    for i in range(len(_STOPS) - 1):
        p0, c0 = _STOPS[i]
        p1, c1 = _STOPS[i + 1]
        if u <= p1:
            t = (u - p0) / ((p1 - p0) or 1)
            return [_lerp(c0[0], c1[0], t), _lerp(c0[1], c1[1], t), _lerp(c0[2], c1[2], t)]
    return list(_STOPS[-1][1])


def _c8(v):
    return int(min(255, max(0, v)))


def new_buf():
    return [[[0.0, 0.0, 0.0] for _ in range(N)] for _ in range(N)]  # buf[y][x] = [r,g,b]


def _set(buf, x, y, r, g, b):
    x, y = round(x), round(y)
    if 0 <= x < N and 0 <= y < N:
        p = buf[y][x]
        if r > p[0]:
            p[0] = r
        if g > p[1]:
            p[1] = g
        if b > p[2]:
            p[2] = b


def _add(buf, x, y, r, g, b):
    x, y = round(x), round(y)
    if 0 <= x < N and 0 <= y < N:
        p = buf[y][x]
        p[0] = min(255, p[0] + r)
        p[1] = min(255, p[1] + g)
        p[2] = min(255, p[2] + b)


def _blob(buf, cx, cy, rad, col, inten):
    for y in range(N):
        for x in range(N):
            d = math.hypot(x - cx, y - cy)
            b = max(0.0, 1 - d / rad) * inten
            if b > 0.02:
                _add(buf, x, y, col[0] * b, col[1] * b, col[2] * b)


# ---------------- renderers ----------------
def ring(buf, disp, t):
    cx, cy = 7.5, 7.5
    prog = disp / 100.0
    col = ramp(prog)
    for y in range(N):
        for x in range(N):
            dx, dy = x - cx, y - cy
            r = math.hypot(dx, dy)
            if r < 4.6 or r > 7.4:
                continue
            a = math.atan2(dy, dx) + math.pi / 2
            if a < 0:
                a += 2 * math.pi
            frac = a / (2 * math.pi)
            rad_edge = 1 - min(abs(r - 6.0) / 1.4, 1)
            if frac <= prog:
                b = 0.5 + 0.5 * rad_edge
                lead = prog - frac
                if 0 <= lead < 0.08:
                    b = min(1.4, b + 0.7 * (1 - lead / 0.08))
                _set(buf, x, y, col[0] * b, col[1] * b, col[2] * b)
            else:
                _set(buf, x, y, 26 * rad_edge, 28 * rad_edge, 36 * rad_edge)
    pulse = 0.55 + 0.45 * math.sin(t * 2.4)
    _blob(buf, cx, cy, 2.0, col, 0.55 * pulse)


def equalizer(buf, disp, t):
    u = disp / 100.0
    base = u * 16
    for x in range(N):
        h = base + math.sin(t * 3 + x * 0.9) * 1.3 + math.sin(t * 5.3 - x * 0.5) * 0.6
        h = max(0.0, min(16.0, h))
        for y in range(N):
            from_b = 15 - y
            if from_b < h:
                frac = from_b / 16
                col = ramp(max(u, frac))
                if h - from_b < 1:  # bright cap
                    _set(buf, x, y, min(255, col[0] * 0.6 + 150),
                         min(255, col[1] * 0.6 + 150), min(255, col[2] * 0.6 + 150))
                else:
                    b = 0.45 + 0.4 * frac
                    _set(buf, x, y, col[0] * b, col[1] * b, col[2] * b)


def error_x(buf, t):
    """Red diagonal cross — unambiguous vs a high-usage red gauge."""
    r = 150 + 60 * (0.5 + 0.5 * math.sin(t * 3))  # gentle pulse
    for i in range(N):
        _set(buf, i, i, r, 24, 24)
        _set(buf, i, 15 - i, r, 24, 24)


# ---------------- usage fetch (stdlib only) ----------------
def _load_creds():
    with open(CREDS) as f:
        return json.load(f)["claudeAiOauth"]


def _save_creds(oauth):
    with open(CREDS) as f:
        data = json.load(f)
    data["claudeAiOauth"].update(oauth)
    tmp = CREDS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CREDS)


def _refresh(oauth):
    """Trade refreshToken for a fresh accessToken; persist back."""
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": oauth["refreshToken"],
        "client_id": CLIENT_ID,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        tok = json.load(resp)
    updated = {
        "accessToken": tok["access_token"],
        "refreshToken": tok.get("refresh_token", oauth["refreshToken"]),
        "expiresAt": int(time.time() * 1000) + int(tok["expires_in"]) * 1000,
    }
    _save_creds(updated)
    oauth.update(updated)
    return oauth


def _get_usage(token):
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "anthropic-version": "2023-06-01",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def fetch_util():
    """Return 5-hour session utilization (0-100). Refreshes token on expiry/401."""
    oauth = _load_creds()
    if oauth.get("expiresAt", 0) - time.time() * 1000 < 60_000:
        oauth = _refresh(oauth)
    try:
        data = _get_usage(oauth["accessToken"])
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403):
            raise
        oauth = _refresh(oauth)
        data = _get_usage(oauth["accessToken"])
    return float(data["five_hour"]["utilization"])


# ---------------- main loop ----------------
class State:
    target = 0.0
    fails = 0


def _fetch_loop(state):
    while True:
        try:
            state.target = fetch_util()
            state.fails = 0
        except Exception as e:  # offline / auth dead -> keep last, count failures
            state.fails += 1
            print("fetch failed:", e)
        time.sleep(FETCH_SECS)


def run(mock=False):
    try:
        import unicornhathd as u
        print("backend: real unicornhathd (physical HAT)")
    except ImportError as e:
        print(f"backend: SIMULATOR (real unicornhathd not importable: {e})")
        from unicorn_hat_sim import unicornhathd as u
    u.rotation(ROTATION)
    u.brightness(BRIGHTNESS)

    state = State()
    if not mock:
        threading.Thread(target=_fetch_loop, args=(state,), daemon=True).start()

    disp = 0.0
    start = time.time()
    try:
        while True:
            t = time.time() - start
            if mock:  # triangle sweep 0..100 to eyeball ramp/edges
                state.target = abs((t * 10) % 200 - 100)
            disp += (state.target - disp) * EASE
            buf = new_buf()
            if state.fails >= 2:
                error_x(buf, t)
            elif int(t // CYCLE_SECS) % 2 == 0:
                ring(buf, disp, t)
            else:
                equalizer(buf, disp, t)
            for y in range(N):
                for x in range(N):
                    r, g, b = buf[y][x]
                    u.set_pixel(x, y, _c8(r), _c8(g), _c8(b))
            u.show()
            time.sleep(1 / FPS)
    except KeyboardInterrupt:
        u.off()


# ---------------- self-check ----------------
def test():
    assert ramp(0)[1] > 180 and ramp(0)[0] < 80, "ramp(0) should be green"
    assert ramp(1)[0] > 180 and ramp(1)[1] < 100, "ramp(1) should be red"

    def lit(buf):
        return sum(1 for row in buf for px in row if max(px) > 2)

    def ok_vals(buf):  # design may overshoot 255; we only require non-negative & finite
        return all(c >= 0 and math.isfinite(c) and _c8(c) <= 255
                   for row in buf for px in row for c in px)

    for r in (ring, equalizer):
        for d in (0, 50, 100):
            b = new_buf()
            r(b, d, 1.23)
            assert ok_vals(b), f"{r.__name__}@{d} bad values"
        assert lit(b) > 0, f"{r.__name__} drew nothing at 100"

    # equalizer fills more at higher usage
    lo, hi = new_buf(), new_buf()
    equalizer(lo, 10, 0.0)
    equalizer(hi, 90, 0.0)
    assert lit(hi) > lit(lo), "equalizer should fill more with higher usage"

    b = new_buf()
    error_x(b, 0.0)
    assert lit(b) > 0, "error glyph drew nothing"
    print("ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="sweep value 0-100 (no network)")
    ap.add_argument("--test", action="store_true", help="run self-checks and exit")
    args = ap.parse_args()
    if args.test:
        test()
    else:
        run(mock=args.mock)
