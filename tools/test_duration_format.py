#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.tg_audio import format_duration

def run():
    cases = [
        (76, "1:16"),
        (76.0, "1:16"),
        ("76.0", "1:16"),
        (0, "0:00"),
        (5, "0:05"),
        (125, "2:05"),
        (None, ""),
    ]
    ok = True
    for val, want in cases:
        got = format_duration(val)
        print(f"val={val!r} -> {got} (want {want})")
        if got != want:
            ok = False
    print("\nRESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(run())