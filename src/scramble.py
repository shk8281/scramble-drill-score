"""
src/scramble.py
---------------
Build the scramble-throw dataset:
  - Plays where the QB scrambled AND threw (passResult in C, I, IN).
  - Tracking frames for those plays only.
  - PFF role (pff_role) merged in from pffScoutingData on gameId/playId/nflId.
  - Player name and position merged in from players on nflId.
"""

import pandas as pd

from src.load import load_plays, load_pff, load_players, load_tracking_for_plays

# passResult codes that mean the QB actually threw the ball.
THROW_RESULTS = {"C", "I", "IN"}


def get_scramble_plays() -> pd.DataFrame:
    """
    Return the subset of plays.csv where:
      - dropBackType contains "SCRAMBLE" (case-insensitive)
      - passResult is C, I, or IN  (the QB threw, not just ran)
    """
    plays = load_plays()
    mask = (
        plays["dropBackType"].str.contains("SCRAMBLE", case=False, na=False)
        & plays["passResult"].isin(THROW_RESULTS)
    )
    return plays[mask].copy()


def build_scramble_tracking() -> pd.DataFrame:
    """
    Load tracking data for every scramble-throw play, then merge in
    pff_role from pffScoutingData and displayName/officialPosition from players.

    Returns
    -------
    pd.DataFrame
        One row per player-frame for scramble-throw plays, with columns:
        all original tracking columns + pff_role + displayName + officialPosition.
    """
    scramble_plays = get_scramble_plays()

    play_keys = set(
        zip(scramble_plays["gameId"], scramble_plays["playId"])
    )

    tracking = load_tracking_for_plays(play_keys)

    # Merge PFF role.
    pff = load_pff()[["gameId", "playId", "nflId", "pff_role"]]
    tracking = tracking.merge(pff, on=["gameId", "playId", "nflId"], how="left")

    # Merge player name and position.
    players = load_players()[["nflId", "displayName", "officialPosition"]]
    # nflId in tracking is float after dropna; cast to match players (int).
    tracking["nflId"] = tracking["nflId"].astype(int)
    tracking = tracking.merge(players, on="nflId", how="left")

    return tracking
