#!/usr/bin/env python3
"""Demo: drives the physical HAT with fake data (no network, no real usage).

Sweeps 0->100->0 so you see the full green->red range, switching between the
Ring gauge and the Equalizer every few seconds. Reuses monitor.py's renderers.

    python3 demo.py
"""
import time

import monitor
from monitor import N, _c8, equalizer, new_buf, ring

SWEEP_SECS = 8     # one full 0->100->0 sweep
SWITCH_SECS = 12   # how long each visualization shows


def main():
    try:
        import unicornhathd as u
        print("backend: real unicornhathd (physical HAT)")
    except ImportError as e:
        print(f"backend: SIMULATOR ({e})")
        from unicorn_hat_sim import unicornhathd as u
    u.rotation(monitor.ROTATION)
    u.brightness(monitor.BRIGHTNESS)

    renderers = [ring, equalizer]
    start = time.time()
    try:
        while True:
            t = time.time() - start
            disp = abs((t / SWEEP_SECS * 200) % 200 - 100)        # triangle 0..100..0
            render = renderers[int(t // SWITCH_SECS) % len(renderers)]
            buf = new_buf()
            render(buf, disp, t)
            for y in range(N):
                for x in range(N):
                    r, g, b = buf[y][x]
                    u.set_pixel(x, y, _c8(r), _c8(g), _c8(b))
            u.show()
            time.sleep(1 / monitor.FPS)
    except KeyboardInterrupt:
        u.off()


if __name__ == "__main__":
    main()
