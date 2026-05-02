from __future__ import annotations

import argparse
import hashlib
import sys
import time

from spqr.bootstrap import new_game
from spqr.engine.tick import Engine
from spqr.persistence import encode_bytes, load_from_path
from spqr.sim.systems import default_systems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spqr", description="Roman city simulation")
    parser.add_argument("--seed", type=int, default=42, help="World seed")
    parser.add_argument(
        "--load", type=str, default=None, help="Path to a save file to load"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without TUI; advance --ticks and print summary",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=1000,
        help="Number of ticks to run in headless mode",
    )
    parser.add_argument(
        "--hash-only",
        action="store_true",
        help="In headless mode, only print the final state hash",
    )
    args = parser.parse_args(argv)

    if args.load:
        state = load_from_path(args.load)
    else:
        state = new_game(seed=args.seed)

    if args.headless:
        engine = Engine(state, default_systems())
        t0 = time.perf_counter()
        engine.step(args.ticks)
        elapsed = time.perf_counter() - t0
        engine.capture_rng()
        digest = hashlib.sha256(encode_bytes(state)).hexdigest()
        if args.hash_only:
            print(digest)
            return 0
        city = state.player_city()
        d = city.districts[0]
        y, m, day = state.date()
        print(f"Ticks: {state.tick} ({elapsed*1000:.1f} ms, {args.ticks/elapsed:.0f}/s)")
        print(f"Date:  AUC {y} {m:02d}/{day:02d} {state.hour():02d}:00")
        print(f"City:  {city.name}")
        print(f"Pops:  {sum(dd.pops.total() for dd in city.districts):.0f}")
        print(f"Grain: {city.treasury.grain:.0f}  Denarii: {city.treasury.denarii:.0f}")
        print(f"Sat:   {d.satisfaction:.2f}  Unrest: {d.pops.unrest:.2f}")
        print(f"Hash:  {digest[:16]}")
        return 0

    # Lazy-import the TUI so headless runs don't require a working terminal.
    from spqr.ui.app import run_app
    run_app(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
