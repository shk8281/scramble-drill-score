"""
src/load.py
-----------
Functions to load the core CSV tables and tracking data.
"""

import pathlib
import pandas as pd

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
TRACKING_DIR = DATA_DIR / "tracking"


def load_plays() -> pd.DataFrame:
    """Load play-level data from plays.csv."""
    return pd.read_csv(DATA_DIR / "plays.csv")


def load_pff() -> pd.DataFrame:
    """Load PFF scouting data from pffScoutingData.csv."""
    return pd.read_csv(DATA_DIR / "pffScoutingData.csv")


def load_players() -> pd.DataFrame:
    """Load player metadata from players.csv."""
    return pd.read_csv(DATA_DIR / "players.csv")


def load_games() -> pd.DataFrame:
    """Load game metadata from games.csv."""
    return pd.read_csv(DATA_DIR / "games.csv")


def load_tracking_for_plays(play_keys: set[tuple]) -> pd.DataFrame:
    """
    Load tracking rows for a specific set of (gameId, playId) pairs.

    Loops over every tracking_<gameId>.csv file, keeps only rows whose
    (gameId, playId) pair is in play_keys, and drops ball rows (nflId is NaN).

    Parameters
    ----------
    play_keys : set of (gameId, playId) tuples
        Only rows matching these pairs are kept.

    Returns
    -------
    pd.DataFrame
        Concatenated tracking rows for the requested plays, ball rows removed.
    """
    # Build a lookup: gameId -> set of playIds for quick per-file filtering.
    game_to_plays: dict[int, set] = {}
    for game_id, play_id in play_keys:
        game_to_plays.setdefault(game_id, set()).add(play_id)

    chunks: list[pd.DataFrame] = []

    for path in sorted(TRACKING_DIR.glob("tracking_*.csv")):
        # Extract gameId from filename (tracking_<gameId>.csv).
        game_id = int(path.stem.split("_", 1)[1])

        if game_id not in game_to_plays:
            continue

        df = pd.read_csv(path)

        # Drop ball rows (nflId is NaN for the ball).
        df = df.dropna(subset=["nflId"])

        # Keep only the requested plays for this game.
        wanted_plays = game_to_plays[game_id]
        df = df[df["playId"].isin(wanted_plays)]

        if not df.empty:
            chunks.append(df)

    if not chunks:
        return pd.DataFrame()

    return pd.concat(chunks, ignore_index=True)
