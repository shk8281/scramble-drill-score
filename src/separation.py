"""
src/separation.py
-----------------
Compute receiver separation at scramble start and at throw for every
scramble-throw play.

Key definitions
---------------
- snap_frame       : first frame where event in {"ball_snap", "autoevent_ballsnap"}
- throw_frame      : first frame where event in {"pass_forward", "autoevent_passforward"}
- scramble_start_frame : first frame BETWEEN snap and throw where the QB
                     (pff_role == "Pass") has moved more than 3 yards
                     laterally (|y - y_at_snap| > 3) from his snap position
- sep_start / sep_throw : for each "Pass Route" player, distance to the
                     nearest "Coverage" player at that frame, computed with
                     numpy broadcasting -- no Python loops over players
- sep_gained       : sep_throw - sep_start

Outputs
-------
output/receivers.csv  -- one row per receiver per kept play
"""

import pathlib
import numpy as np
import pandas as pd

from src.scramble import build_scramble_tracking

OUTPUT_DIR = pathlib.Path(__file__).parent.parent / "output"

SNAP_EVENTS = {"ball_snap", "autoevent_ballsnap"}
THROW_EVENTS = {"pass_forward", "autoevent_passforward"}

LATERAL_THRESHOLD_YDS = 3.0  # yards off snap y-position to call it a scramble


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _first_frame(play_df: pd.DataFrame, events: set[str]) -> int | None:
    """Return the first frameId where event is in `events`, or None."""
    mask = play_df["event"].isin(events)
    if not mask.any():
        return None
    return int(play_df.loc[mask, "frameId"].iloc[0])


def _xy_at_frame(play_df: pd.DataFrame, nfl_id: int, frame: int) -> tuple[float, float] | None:
    """Return (x, y) for a player at a specific frame, or None if missing."""
    row = play_df[(play_df["nflId"] == nfl_id) & (play_df["frameId"] == frame)]
    if row.empty:
        return None
    return float(row["x"].iloc[0]), float(row["y"].iloc[0])


def _min_distance_vectorized(
    receivers: pd.DataFrame, defenders: pd.DataFrame
) -> np.ndarray:
    """
    For each receiver return the distance to the nearest defender.

    Uses numpy broadcasting -- no Python loop over individual players.

    Parameters
    ----------
    receivers : DataFrame with columns x, y; shape (R,)
    defenders : DataFrame with columns x, y; shape (D,)

    Returns
    -------
    np.ndarray of shape (R,) with the minimum distance for each receiver.
    Returns np.nan for any receiver when there are no defenders.
    """
    if defenders.empty or receivers.empty:
        return np.full(len(receivers), np.nan)

    rx = receivers["x"].to_numpy()[:, np.newaxis]   # (R, 1)
    ry = receivers["y"].to_numpy()[:, np.newaxis]   # (R, 1)
    dx = defenders["x"].to_numpy()[np.newaxis, :]   # (1, D)
    dy = defenders["y"].to_numpy()[np.newaxis, :]   # (1, D)

    distances = np.hypot(rx - dx, ry - dy)          # (R, D)
    return distances.min(axis=1)                     # (R,)


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_separation() -> pd.DataFrame:
    """
    Build the receiver-level separation table for all scramble-throw plays.

    Returns
    -------
    pd.DataFrame with columns:
        gameId, playId, nflId, displayName, officialPosition,
        scramble_duration_sec, sep_start, sep_throw, sep_gained
    """
    tracking = build_scramble_tracking()

    plays_kept: list[pd.DataFrame] = []
    n_skipped = 0
    skip_reasons: dict[str, int] = {
        "no_snap": 0,
        "no_throw": 0,
        "no_qb_at_snap": 0,
        "no_scramble_start": 0,
        "no_receivers": 0,
        "no_defenders": 0,
    }

    for (game_id, play_id), play_df in tracking.groupby(["gameId", "playId"]):

        # --- locate key frames ---
        snap_frame = _first_frame(play_df, SNAP_EVENTS)
        if snap_frame is None:
            skip_reasons["no_snap"] += 1
            n_skipped += 1
            continue

        throw_frame = _first_frame(play_df, THROW_EVENTS)
        if throw_frame is None:
            skip_reasons["no_throw"] += 1
            n_skipped += 1
            continue

        # --- identify the QB ---
        qb_rows = play_df[play_df["pff_role"] == "Pass"]
        if qb_rows.empty:
            skip_reasons["no_qb_at_snap"] += 1
            n_skipped += 1
            continue

        qb_id = int(qb_rows["nflId"].iloc[0])
        qb_snap = _xy_at_frame(play_df, qb_id, snap_frame)
        if qb_snap is None:
            skip_reasons["no_qb_at_snap"] += 1
            n_skipped += 1
            continue

        qb_snap_y = qb_snap[1]

        # --- find scramble start: first frame in [snap, throw] where QB moved
        #     more than 3 yards laterally (y-axis) ---
        between = play_df[
            (play_df["nflId"] == qb_id)
            & (play_df["frameId"] >= snap_frame)
            & (play_df["frameId"] <= throw_frame)
        ].sort_values("frameId")

        moved = between[np.abs(between["y"] - qb_snap_y) > LATERAL_THRESHOLD_YDS]
        if moved.empty:
            skip_reasons["no_scramble_start"] += 1
            n_skipped += 1
            continue

        scramble_start_frame = int(moved["frameId"].iloc[0])
        scramble_duration_sec = (throw_frame - scramble_start_frame) / 10.0

        # --- receivers and defenders at each key frame ---
        def players_at(frame: int, role: str) -> pd.DataFrame:
            return play_df[
                (play_df["frameId"] == frame) & (play_df["pff_role"] == role)
            ][["nflId", "displayName", "officialPosition", "x", "y"]]

        recv_start = players_at(scramble_start_frame, "Pass Route")
        recv_throw = players_at(throw_frame, "Pass Route")
        def_start = players_at(scramble_start_frame, "Coverage")
        def_throw = players_at(throw_frame, "Coverage")

        if recv_start.empty or recv_throw.empty:
            skip_reasons["no_receivers"] += 1
            n_skipped += 1
            continue

        if def_start.empty or def_throw.empty:
            skip_reasons["no_defenders"] += 1
            n_skipped += 1
            continue

        # --- vectorized separation distances ---
        sep_start_vals = _min_distance_vectorized(recv_start, def_start)
        sep_throw_vals = _min_distance_vectorized(recv_throw, def_throw)

        # Build result rows, joining start and throw on nflId.
        start_df = recv_start[["nflId", "displayName", "officialPosition"]].copy()
        start_df["sep_start"] = sep_start_vals

        throw_df = recv_throw[["nflId"]].copy()
        throw_df["sep_throw"] = sep_throw_vals

        merged = start_df.merge(throw_df, on="nflId", how="inner")
        if merged.empty:
            n_skipped += 1
            continue

        merged.insert(0, "playId", play_id)
        merged.insert(0, "gameId", game_id)
        merged["scramble_duration_sec"] = scramble_duration_sec
        merged["sep_gained"] = merged["sep_throw"] - merged["sep_start"]

        plays_kept.append(merged)

    if not plays_kept:
        result = pd.DataFrame(columns=[
            "gameId", "playId", "nflId", "displayName", "officialPosition",
            "scramble_duration_sec", "sep_start", "sep_throw", "sep_gained",
        ])
    else:
        result = pd.concat(plays_kept, ignore_index=True)[
            [
                "gameId", "playId", "nflId", "displayName", "officialPosition",
                "scramble_duration_sec", "sep_start", "sep_throw", "sep_gained",
            ]
        ]

    # Persist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_DIR / "receivers.csv", index=False)

    # Attach skip-reason summary as an attribute for the __main__ block.
    result._skip_reasons = skip_reasons   # type: ignore[attr-defined]
    result._n_skipped = n_skipped         # type: ignore[attr-defined]

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Building scramble tracking and computing separation...")
    df = compute_separation()

    skip_reasons = getattr(df, "_skip_reasons", {})
    n_skipped = getattr(df, "_n_skipped", 0)
    n_plays_kept = df[["gameId", "playId"]].drop_duplicates().shape[0]

    print(f"\nPlays kept  : {n_plays_kept:,}")
    print(f"Plays skipped: {n_skipped:,}")
    if skip_reasons:
        for reason, count in skip_reasons.items():
            if count:
                print(f"  {reason}: {count}")

    if df.empty:
        print("\nNo data -- nothing more to report.")
    else:
        med_dur = df["scramble_duration_sec"].median()
        print(f"\nMedian scramble_duration_sec : {med_dur:.2f} s")

        print("\nMean sep_gained and receiver count by officialPosition:")
        summary = (
            df.groupby("officialPosition")["sep_gained"]
            .agg(mean_sep_gained="mean", count="count")
            .sort_values("count", ascending=False)
        )
        print(summary.to_string())

    print(f"\nSaved output/receivers.csv  ({len(df):,} rows)")
