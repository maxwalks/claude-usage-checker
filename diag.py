#!/usr/bin/env python3
"""Diagnostics for the Claude usage monitor. Run on the Pi:

    python3 diag.py            # test both fetch + hardware
    python3 diag.py fetch      # just the usage API
    python3 diag.py hw         # just light the physical matrix

Tells you exactly why the display is blank and/or the fetch 403s.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import monitor  # reuse the same constants/headers


def fetch():
    print("== USAGE FETCH ==")
    if not os.path.exists(monitor.CREDS):
        print("  NO credentials file at", monitor.CREDS)
        print("  -> run `claude` and log in on this Pi, or copy the file from your dev box")
        return
    o = json.load(open(monitor.CREDS))["claudeAiOauth"]
    tok = o.get("accessToken", "")
    print("  access token:", "present" if tok else "MISSING", f"(len {len(tok)})")
    exp = o.get("expiresAt", 0)
    print("  expiresAt:", exp, "->", round((exp - time.time() * 1000) / 1000), "s from now",
          "(EXPIRED)" if exp and exp < time.time() * 1000 else "")
    print("  scopes:", o.get("scopes"))
    print("  subscriptionType:", o.get("subscriptionType"))
    req = urllib.request.Request(monitor.USAGE_URL, headers={
        "Authorization": f"Bearer {tok}",
        "anthropic-beta": "oauth-2025-04-20",
        "anthropic-version": "2023-06-01",
        "User-Agent": monitor.USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        print("  OK -> 5h util:", d["five_hour"]["utilization"],
              " 7d util:", d["seven_day"]["utilization"])
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} {e.reason}")
        print("  body:", e.read().decode(errors="replace")[:600])
        if e.code in (401, 403):
            print("  -> token rejected. Re-login on the Pi: `claude` then /login,")
            print("     or copy a fresh ~/.claude/.credentials.json from your dev box.")
    except Exception as e:
        print("  FAILED:", repr(e))


def hw():
    print("== HARDWARE ==")
    try:
        import unicornhathd as u
        print("  real unicornhathd imported OK")
    except Exception as e:
        print("  REAL LIB IMPORT FAILED:", repr(e))
        print("  -> this is why nothing shows on the physical HAT.")
        print("     Enable SPI (sudo raspi-config -> Interface -> SPI) and install the lib:")
        print("     sudo pip install unicornhathd --break-system-packages")
        return
    try:
        u.rotation(0)
        u.brightness(0.6)
        for name, (r, g, b) in [("red", (255, 0, 0)), ("green", (0, 255, 0)),
                                ("blue", (0, 0, 255)), ("white", (110, 110, 110))]:
            print("  filling", name, "...")
            for x in range(16):
                for y in range(16):
                    u.set_pixel(x, y, r, g, b)
            u.show()
            time.sleep(1.2)
        u.off()
        print("  done -> did the matrix flash red/green/blue/white?")
        print("     no -> check SPI enabled + ribbon seated; try `sudo python3 diag.py hw`")
    except Exception as e:
        print("  lib imported but show() failed:", repr(e))
        print("  -> usually SPI not enabled or needs sudo for /dev/spidev*")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("fetch", "all"):
        fetch()
        print()
    if what in ("hw", "all"):
        hw()
