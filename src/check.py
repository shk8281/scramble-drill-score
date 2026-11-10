"""
src/check.py
------------
Quick sanity-check script.  Run with:
    .venv\\Scripts\\python.exe -m src.check

Prints table shapes, key value counts, and the number of scramble-throw plays.
Expected: ~8,557 rows in plays.csv, ~567 scramble-throw plays.
"""

import pandas as pd

from src.load import load_plays, load_pff, load_players, load_games
from src.scramble import get_scramble_plays, build_scramble_tracking


def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


def main() -> None:
    # --- Core tables ---
    _section("Table shapes")
    plays = load_plays()
    pff = load_pff()
    players = load_players()
    games = load_games()

    for name, df in [
        ("plays.csv", plays),
        ("pffScoutingData.csv", pff),
        ("players.csv", players),
        ("games.csv", games),
    ]:
        print(f"  {name:30s}  {df.shape[0]:>7,} rows  x  {df.shape[1]:>3} cols")

    # --- passResult distribution ---
    _section("passResult value counts (plays.csv)")
    print(plays["passResult"].value_counts(dropna=False).to_string())

    # --- dropBackType distribution ---
    _section("dropBackType value counts (plays.csv)")
    print(plays["dropBackType"].value_counts(dropna=False).to_string())

    # --- Scramble-throw plays ---
    _section("Scramble-throw plays")
    scramble = get_scramble_plays()
    n = len(scramble)
    print(f"  Plays where QB scrambled and threw: {n:,}")
    print(f"  (Expected: ~567)")

    if n > 0:
        print("\n  passResult breakdown within scramble-throw plays:")
        print(scramble["passResult"].value_counts().to_string())

    # --- Tracking spot-check ---
    _section("Tracking spot-check (first 5 scramble-throw plays)")
    if n == 0:
        print("  No scramble-throw plays found -- skipping tracking load.")
        return

    sample_plays = scramble.head(5)
    sample_keys = set(zip(sample_plays["gameId"], sample_plays["playId"]))

    from src.load import load_tracking_for_plays
    sample_tracking = load_tracking_for_plays(sample_keys)
    print(f"  Tracking rows for 5 plays: {len(sample_tracking):,}")
    print(f"  Columns: {sample_tracking.columns.tolist()}")


if __name__ == "__main__":
    main()
