# SPQR

A terminal-based Roman city simulator — Dwarf Fortress × SimCity in the
ancient Mediterranean. Procedurally generated province, deterministic
tick-based simulation, Textual TUI.

This document covers installation and the `spqr` command-line interface
only. For gameplay, launch the TUI and explore in-game.

## Requirements

- Python 3.12 or newer
- A terminal capable of rendering [Textual](https://textual.textualize.io/)
  (kitty, alacritty, iTerm2, Windows Terminal, GNOME Terminal, etc.)
- No system packages or environment variables required

## Install

```bash
git clone <this-repo> spqr
cd spqr
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The `[dev]` extra adds `pytest` and `pytest-asyncio`. For a runtime-only
install, drop the extra:

```bash
pip install -e .
```

Installing exposes a `spqr` console script in addition to `python -m spqr`;
both invoke the same entry point.

## Run

Launch the TUI:

```bash
spqr                                    # or: python -m spqr
spqr --seed 1234                        # specific world seed
spqr --load saves/quick.spqr            # resume from a save
spqr --no-splash                        # skip the start screen
```

The same world seed always generates the same world.

## Headless mode

Run the simulation without a TUI — useful for CI, balance testing, or
determinism checks:

```bash
spqr --headless --seed 42 --ticks 5000
```

Prints a one-shot summary: date, city name, population, treasury, and
the truncated state hash.

For a determinism check, use `--hash-only` to print only the final hash:

```bash
spqr --headless --seed 42 --ticks 5000 --hash-only
spqr --headless --seed 42 --ticks 5000 --hash-only
# both runs print the same hash
```

## Save files

Save files are written to `saves/` relative to the current working
directory. The directory is created on first save. The TUI's quick
save/load (`s`/`l` in-game) uses `saves/quick.spqr`. To resume any save
from the command line, pass its path to `--load`.

## CLI reference

| Flag           | Default | Description |
| -------------- | ------- | ----------- |
| `--seed N`     | `42`    | World seed (deterministic — same seed → same world). |
| `--load PATH`  | —       | Load a save file instead of generating a new world. |
| `--headless`   | off     | Run without the TUI; advance `--ticks` and print a summary. |
| `--ticks N`    | `1000`  | Number of ticks to advance in headless mode. |
| `--hash-only`  | off     | With `--headless`, print only the final state hash. |
| `--no-splash`  | off     | Skip the start-of-game splash and bootstrap directly with the existing-village default. |

One tick is one in-game hour.

## Tests

`pytest` is installed by the `[dev]` extra. With the venv activated
(`source .venv/bin/activate`), run:

```bash
pytest
```

If you see `pytest: command not found`, either the venv isn't active in
the current shell or you installed without the `[dev]` extra — re-run
`pip install -e ".[dev]"` and try again.
