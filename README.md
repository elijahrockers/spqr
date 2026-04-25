# SPQR

A terminal-based Roman city simulator — Dwarf Fortress × SimCity in the
ancient Mediterranean. Procedurally generated province, hybrid
agent/aggregate population, deterministic tick-based simulation.

This is an engine-first MVP: world generates, time advances, a small
settlement runs itself, and you nudge it via zoning and policy.

## Requirements

- Python 3.12 or newer
- A terminal that can render Textual (any modern terminal: kitty, alacritty,
  iTerm2, Windows Terminal, GNOME Terminal, etc.)

## Install

```bash
git clone <this-repo> spqr   # or use your existing checkout
cd spqr
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

Launch the TUI with a default seed:

```bash
python -m spqr
```

Pick a specific seed (same seed always generates the same world):

```bash
python -m spqr --seed 1234
```

Resume a save:

```bash
python -m spqr --load saves/quick.spqr
```

Run headless for a fixed number of ticks (useful for CI or balance
testing):

```bash
python -m spqr --headless --seed 42 --ticks 5000
python -m spqr --headless --seed 42 --ticks 5000 --hash-only
```

## Controls

| Key       | Action                                    |
|-----------|-------------------------------------------|
| `space`   | Toggle pause                              |
| `+` / `-` | Speed up / slow down (PAUSED → 64×)       |
| `c`       | City view                                 |
| `r`       | Region view                               |
| arrows    | Move the cursor (city view)               |
| `b`       | Open the **build menu** (pick a zone tool)|
| `p`       | Open the **population screen**            |
| `i`       | Open the **info screen** for the building under the cursor |
| `enter`   | Anchor first corner; press again to commit a rectangle |
| `escape`  | Cancel: drag → range highlight (in that order) |
| `s`       | Save to `saves/quick.spqr`                |
| `l`       | Load from `saves/quick.spqr`              |
| `q`       | Quit                                      |

### Build menu

Press `b` to open. The menu lists the available zones with their hotkeys:

| Key | Zone      | Cost (d/t/s) | Notes                              |
|-----|-----------|--------------|------------------------------------|
| `1` | Farm      | 20 / 10 / 0  | 6 worker slots; produces grain     |
| `2` | Insula    | 50 / 20 / 10 | housing for 40 plebs               |
| `3` | Barracks  | 80 / 15 / 20 | soldier housing; +50 storage       |
| `4` | Granary   | 40 / 15 / 10 | grain storage; 2 worker slots      |
| `5` | Workshop  | 60 / 15 / 10 | 4 workers; future goods            |
| `6` | Road      | 5 / 0 / 2    | connects tiles                     |
| `7` | Warehouse | 80 / 20 / 20 | +250 materials storage             |
| `0` | Clear     | —            | drops the active tool              |

`d` denarii, `t` timber, `s` stone. Cost is paid at designation. If you
designate a rectangle larger than your treasury can afford, only as many
tiles as you can pay for are placed; the rest are skipped.

Press `escape` (or `b` again) to leave the menu without changing the
current tool. The active brush is shown in the bottom status bar and an
asterisk marks it inside the menu.

### Population screen

Press `p` to view your city's population at a glance: class composition
(patricians / equites / plebs / slaves), labor utilization (workforce,
worker slots, assigned, idle), housing capacity vs. homeless, and per-
district satisfaction and unrest. The screen refreshes live while the
sim runs underneath. `escape` or `p` closes it.

### Info screen

Press `i` while the cursor is over a building to open the info screen.
For a **granary**, the screen offers two extra hotkeys:

- `r` — **highlight range** on the city map. The granary's coverage
  tiles render with a teal background so you can see at a glance which
  insulae, domus, barracks, and farms it can serve. `escape` from the
  main view clears the highlight.
- `g` — **inventory graph**. ASCII bar chart of historical grain
  inventory using up to 30 game days of stored samples. Inside the
  graph, press `d` to toggle between hourly resolution (last ~60 hours)
  and daily resolution (per-day average for up to 30 days). `escape`
  closes the graph.

Other building kinds show a generic info pane for now.

### Designating zones in a rectangle

Pick a tool (e.g. `1` for Farm), move the cursor to one corner, press
`enter` to anchor. The cell turns yellow. Move to the opposite corner —
the bounding rectangle highlights every tile inside it: green where the
zone will be placed, red where it'll be skipped (water, rock,
forest/hill, or already-occupied tiles). Press `enter` again to commit,
or `escape` to cancel. A 1×1 rectangle (anchor and commit on the same
cell) is a single-tile placement.

## Reading the screen

- **City map glyphs:** `.` grass · `T` forest · `^` hill · `~` water ·
  `#` rock · `=` road. Buildings: `F` forum · `h` insula · `f` farm ·
  `G` granary · `B` barracks · `W` workshop · `S` warehouse · `t` temple.
  Buildings rendered dim are still under construction.
- **Region map glyphs:** `@` your city · `X` barbarian camp · biomes
  follow the same convention as city terrain, plus `M` for mountain.
- **Status bar (bottom):** city name · in-game date (AUC year/month/day)
  and hour · grain stock · denarii · total population · garrison size ·
  current speed · current zone tool.
- **Tile inspector (right, top):** stats for whatever the cursor is
  hovering over. Empty tiles show terrain and buildability. Buildings
  show kind, completion, workers (assigned/slots), district. Farms
  show a crop-maturity bar, the current season (growing/dormant),
  grain awaiting transport, and yield per harvest. Granaries show
  current grain inventory vs. capacity. Insulae and domus show how
  many granaries are within reach (and total grain in those
  granaries) plus the resident class and meal cadence. Storage-bearing
  buildings (forum, barracks, warehouse) show their capacity and the
  city's current timber/stone stocks vs. total storage cap.
- **Annals panel (right, bottom):** rolling event log — births,
  deaths, completions, raids, treasury crises.

## Tips for your first city

- One tick = one in-game hour. At `1×`, simulation matches real time;
  jump to `16×` or `64×` to skip across seasons quickly.
- Founding happens in winter. Your starting grain (~600) is enough to
  reach the spring harvest if you don't waste it. Set the grain dole
  to `0` early if you're tight (this isn't exposed in the menu yet —
  it defaults to 0.5 grain/pleb/month).
- Place farms early. Each farm needs 6 worker slots; only built (full
  brightness) farms produce. Construction also pulls labor — a building
  site with no spare workforce will sit at 0% until labor frees up.
- **Grain is seasonal.** Farms grow crops only during the growing season
  (March–September). A fully-staffed farm matures and harvests every
  ~20 game days, yielding 600 grain per harvest. Outside the growing
  season they sit idle, so the city must stockpile enough to bridge
  October–February. Harvested grain sits on the farm until carted to
  the nearest in-range granary.
- **Granaries feed houses by proximity.** Each granary serves the
  surrounding tiles up to a Dijkstra cost of 12 — that's about 5
  Manhattan tiles in open ground. Roads cost 1 per step (vs. 2.5 for
  plain ground) and dramatically extend a granary's reach. A house
  with no granary in range will starve regardless of total city
  stockpile. Spread granaries; pave roads.
- **Meals are scheduled events**, not a steady drip. Slaves eat once
  every 2 days (around 5 am), plebs once a day (6 am), equites and
  patricians twice a day (7/19 and 9/21), legionaries twice a day
  (6/18). The granary inventory drops in distinct steps at those
  hours and stays flat in between. Daily totals match the old
  continuous rates, but you can now watch the city eat.
- **Soldiers eat too.** Legionaries draw rations from granaries
  serving their barracks at every mess hour. Without an in-range
  granary, the garrison goes hungry — same starvation pipeline as
  civilians.
- The starter city has 150 materials storage (forum 100 + barracks 50)
  and 80 timber + 40 stone in stock. Once you've built a few things
  you'll need a **warehouse** (+250 capacity) to import or stockpile
  more — though there's no production of timber/stone yet, so plan
  early builds carefully.
- Without a barracks, your garrison's training drifts down. Without a
  garrison, raids will succeed and loot the treasury.
- Save (`s`) before risky decisions; load (`l`) restores the last save.

## Verifying / hacking on the engine

Run the test suite:

```bash
pytest
```

Confirm a build is deterministic (same seed → same state hash):

```bash
python -m spqr --headless --seed 42 --ticks 5000 --hash-only
python -m spqr --headless --seed 42 --ticks 5000 --hash-only
# → identical hash
```

For deeper context on architecture, invariants, and gotchas, read
`CLAUDE.md` and `JOURNAL.md`.

## Status

MVP. Working: tick loop, procgen, basic economy, demographics, military
upkeep, raids, save/load, TUI. Not yet implemented: recruitment, trade,
multiple districts, magistrate succession, multi-city play.
