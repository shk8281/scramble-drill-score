"""
src/target.py
-------------
Parse the targeted receiver from plays.playDescription and match to
the receiver rows in output/receivers.csv.

Regex pattern
-------------
Looks for constructions like:
  "... pass short right to T.Hill ..."
  "... pass incomplete deep left intended for D.Hopkins ..."
  "... pass short middle to A.St. Brown ..."

The captured group is the name token after "to"/"intended for":
  Initial (one uppercase letter, optional lowercase) + "."
  Optional "St. " prefix
  Last name starting with an uppercase letter
e.g. "T.Hill", "A.St. Brown", "D.Hopkins".
re.IGNORECASE is intentionally absent -- the data uses title case and the
flag caused the greedy pattern to swallow trailing tokens like "to NYJ".

Matching rule
-------------
Normalise both sides before comparing:
  - Lower-case everything.
  - Strip name suffixes (Jr., Sr., II, III, IV) from displayName.
  - Remove periods and apostrophes.
  - From the description token: take everything after the first "." so
    "t.hill" -> "hill", "a.st. brown" -> "st brown".
  - From displayName: take everything after the first space (i.e. the
    last-name portion), after suffix stripping.
  - Both sides normalised the same way, so "st brown" == "st brown".
  - Only receivers already in output/receivers.csv (Pass Route, that play)
    are considered as candidates.

Throws without a named receiver are excluded entirely from outputs
(not counted as incompletions).

Outputs
-------
output/targets.csv  -- targeted rows for plays matched to exactly one receiver,
                       with added columns: targeted (True), passResult.
"""

import pathlib
import re

import pandas as pd

from src.load import load_plays

OUTPUT_DIR = pathlib.Path(__file__).parent.parent / "output"
RECEIVERS_CSV = OUTPUT_DIR / "receivers.csv"
TARGETS_CSV = OUTPUT_DIR / "targets.csv"

# Capture an initial like "T." or "A." then an optional "St. " prefix,
# then the last name.  NO re.IGNORECASE -- the data uses title case and
# the flag caused the pattern to swallow lowercase words like "to NYJ"
# or "INTERCEPTED by ...".
# Examples matched: "T.Hill", "A.St. Brown", "D.Hopkins"
_TARGET_RE = re.compile(
    r"pass (?:incomplete )?(?:short|deep) \w+ (?:to|intended for) "
    r"([A-Z][a-z]?\.(?:St\. )?[A-Z][A-Za-z'\-]+)"
)

# Name suffixes to strip from displayName before matching.
_SUFFIX_RE = re.compile(
    r"\b(?:jr\.?|sr\.?|ii|iii|iv)\s*$",
    re.IGNORECASE,
)


def _normalise_token(token: str) -> str:
    """
    Normalise a description name token to a comparable key.

    "A.St. Brown"        -> "st brown"
    "T.Hill"             -> "hill"
    "D.J.Moore"          -> "j moore"  (initial dot, then rest)
    "R.Seals-Jones"      -> "sealsjones"
    "J.Westbrook-Ikhine" -> "westbrookikhine"
    """
    # Drop everything up to and including the first ".".
    if "." in token:
        token = token[token.index(".") + 1:]
    # Remove periods, apostrophes, and hyphens; collapse whitespace.
    token = re.sub(r"[.'`\-]", "", token)
    return token.strip().lower()


def _normalise_display(display: str) -> str:
    """
    Normalise a displayName to a comparable key.

    "Amari Cooper"       -> "cooper"
    "Equanimeous St. Brown" -> "st brown"
    "Odell Beckham Jr."  -> "beckham"
    "Ha Ha Clinton-Dix"  -> "clintondix"
    """
    # Strip suffix.
    name = _SUFFIX_RE.sub("", display).strip()
    # Drop first word (first name).
    parts = name.split(None, 1)
    last_part = parts[1] if len(parts) > 1 else parts[0]
    # Remove periods and apostrophes.
    last_part = re.sub(r"[.'`]", "", last_part)
    # Collapse hyphens to nothing (Clinton-Dix -> clintondix).
    last_part = last_part.replace("-", "")
    return last_part.strip().lower()


def build_targets() -> pd.DataFrame:
    """
    Match each scramble-throw play to its targeted receiver.

    Returns
    -------
    pd.DataFrame
        Rows from receivers.csv for plays matched to exactly one receiver,
        with columns: all receivers.csv columns + targeted (True) + passResult.

    Side effects
    ------------
    Saves output/targets.csv.
    Prints a matching-quality report and unmatched tokens.
    """
    receivers = pd.read_csv(RECEIVERS_CSV)
    plays = load_plays()[["gameId", "playId", "playDescription", "passResult"]]

    # Restrict plays to those present in receivers.csv.
    play_keys = receivers[["gameId", "playId"]].drop_duplicates()
    plays = plays.merge(play_keys, on=["gameId", "playId"], how="inner")

    # --- extract named target from play description ---
    plays = plays.copy()
    plays["_target_token"] = plays["playDescription"].apply(
        lambda desc: (
            m.group(1).strip() if (m := _TARGET_RE.search(str(desc))) else None
        )
    )

    n_total = len(plays)
    n_named = plays["_target_token"].notna().sum()
    n_throwaway = n_total - n_named

    # Keep only plays with a named target.
    named = plays[plays["_target_token"].notna()].copy()
    named["_target_norm"] = named["_target_token"].apply(_normalise_token)

    # --- normalise receiver display names ---
    receivers = receivers.copy()
    receivers["_recv_norm"] = receivers["displayName"].apply(_normalise_display)

    # Merge on gameId, playId, then filter on normalised-name match.
    merged = named.merge(receivers, on=["gameId", "playId"], how="left")
    merged["_name_match"] = merged["_target_norm"] == merged["_recv_norm"]
    matched = merged[merged["_name_match"]].copy()

    # Count matches per play.
    match_counts = (
        matched.groupby(["gameId", "playId"])
        .size()
        .rename("_n_matches")
        .reset_index()
    )
    named = named.merge(match_counts, on=["gameId", "playId"], how="left")
    named["_n_matches"] = named["_n_matches"].fillna(0).astype(int)

    n_exactly_one = int((named["_n_matches"] == 1).sum())
    n_none        = int((named["_n_matches"] == 0).sum())
    n_multiple    = int((named["_n_matches"] > 1).sum())

    # --- report ---
    print("\nTargeting parse report")
    print(f"  Total plays in receivers.csv           : {n_total:,}")
    print(f"  Plays with a named target in desc      : {n_named:,}  "
          f"({100 * n_named / n_total:.1f}%)")
    print(f"  Plays with no named target (throwaway) : {n_throwaway:,}")
    print(f"  Named plays matched to exactly 1 recv  : {n_exactly_one:,}")
    print(f"  Named plays matched to 0 receivers     : {n_none:,}")
    print(f"  Named plays matched to 2+ receivers    : {n_multiple:,}")

    # --- report unmatched tokens ---
    unmatched = named[named["_n_matches"] == 0][["_target_token", "_target_norm"]].copy()
    if not unmatched.empty:
        counts = (
            unmatched.groupby(["_target_token", "_target_norm"])
            .size()
            .reset_index(name="plays")
            .sort_values("plays", ascending=False)
        )
        print("\n  Unmatched target tokens (token -> normalised, plays):")
        for _, row in counts.iterrows():
            print(f"    {row['_target_token']:25s} -> {row['_target_norm']:20s}  ({row['plays']}x)")

    # --- build output: exactly-one-match rows ---
    one_match_keys = named[named["_n_matches"] == 1][["gameId", "playId"]]
    targets = matched.merge(one_match_keys, on=["gameId", "playId"], how="inner")
    targets = targets.drop(
        columns=[c for c in targets.columns if c.startswith("_")],
        errors="ignore",
    )
    targets["targeted"] = True

    front_cols = [
        "gameId", "playId", "nflId", "displayName", "officialPosition",
        "scramble_duration_sec", "sep_start", "sep_throw", "sep_gained",
        "targeted", "passResult",
    ]
    extra_cols = [c for c in targets.columns if c not in front_cols]
    targets = targets[front_cols + extra_cols]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    targets.to_csv(TARGETS_CSV, index=False)
    print(f"\n  Saved output/targets.csv ({len(targets):,} rows)")

    return targets


if __name__ == "__main__":
    build_targets()
