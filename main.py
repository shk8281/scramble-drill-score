"""
main.py
-------
Full pipeline for Scramble Drill Score.

Runs in order:
  1. separation.py  -- compute snap/throw/scramble frames and sep_gained
  2. target.py      -- parse targeted receiver from play description
  3. charts.py      -- headline chart + stats + leaderboard

All printed output is tee'd to output/results.txt so README numbers
can be copied from one place.

Usage:
    .venv\\Scripts\\python.exe main.py
"""

import io
import pathlib
import sys

# ---------------------------------------------------------------------------
# Tee: write to both stdout and a file simultaneously.
# ---------------------------------------------------------------------------

OUTPUT_DIR  = pathlib.Path(__file__).parent / "output"
RESULTS_TXT = OUTPUT_DIR / "results.txt"


class _Tee(io.TextIOBase):
    """Wraps two text streams and writes to both."""

    def __init__(self, stream_a: io.TextIOBase, stream_b: io.TextIOBase) -> None:
        self._a = stream_a
        self._b = stream_b

    def write(self, s: str) -> int:
        self._a.write(s)
        self._b.write(s)
        return len(s)

    def flush(self) -> None:
        self._a.flush()
        self._b.flush()


def _setup_tee() -> io.TextIOWrapper:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(RESULTS_TXT, "w", encoding="utf-8")
    tee = _Tee(sys.stdout, log_file)   # type: ignore[arg-type]
    sys.stdout = tee                   # type: ignore[assignment]
    return log_file                    # keep reference so it stays open


def _teardown_tee(original_stdout: io.TextIOBase, log_file: io.IOBase) -> None:
    sys.stdout = original_stdout       # type: ignore[assignment]
    log_file.close()


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def run_separation() -> None:
    from src.separation import compute_separation

    print("=" * 60)
    print("STEP 1  Separation metrics")
    print("=" * 60)
    df = compute_separation()

    skip_reasons = getattr(df, "_skip_reasons", {})
    n_skipped    = getattr(df, "_n_skipped", 0)
    n_kept       = df[["gameId", "playId"]].drop_duplicates().shape[0]

    print(f"Plays kept   : {n_kept:,}")
    print(f"Plays skipped: {n_skipped:,}")
    for reason, count in skip_reasons.items():
        if count:
            print(f"  {reason}: {count}")

    if not df.empty:
        med = df["scramble_duration_sec"].median()
        print(f"\nMedian scramble_duration_sec : {med:.2f} s")
        print("\nMean sep_gained and receiver count by officialPosition:")
        summary = (
            df.groupby("officialPosition")["sep_gained"]
            .agg(mean_sep_gained="mean", count="count")
            .sort_values("count", ascending=False)
        )
        print(summary.to_string())

    print(f"\nSaved output/receivers.csv ({len(df):,} rows)")


def run_targets() -> "pd.DataFrame":  # noqa: F821  (quoted to avoid import at module level)
    from src.target import build_targets

    print("\n" + "=" * 60)
    print("STEP 2  Targeting parse")
    print("=" * 60)
    return build_targets()


def run_charts(targets: "pd.DataFrame") -> None:  # noqa: F821
    from src.charts import headline_chart, leaderboard

    print("\n" + "=" * 60)
    print("STEP 3  Headline chart and statistics")
    print("=" * 60)
    headline_chart(targets)

    print("\n" + "=" * 60)
    print("STEP 4  Leaderboard")
    print("=" * 60)
    leaderboard()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _original_stdout = sys.stdout
    _log_file = _setup_tee()

    try:
        print("Scramble Drill Score -- full pipeline")
        print(f"Output will be saved to {RESULTS_TXT}\n")

        run_separation()
        targets = run_targets()

        # --- sanity checks before charting ---
        n_matched = len(targets)
        if n_matched < 400:
            raise RuntimeError(
                f"Sanity check failed: only {n_matched} plays matched exactly one "
                f"receiver (expected >= 400). Check target.py regex and normalisation."
            )

        overall_comp = (targets["passResult"] == "C").mean()
        if not (0.40 <= overall_comp <= 0.65):
            raise RuntimeError(
                f"Sanity check failed: overall completion rate is {overall_comp:.1%} "
                f"(expected 40%-65%). passResult values may not be joining correctly."
            )

        print(
            f"\nSanity checks passed: {n_matched:,} matched plays, "
            f"{overall_comp:.1%} overall completion rate."
        )

        run_charts(targets)

        print("\n" + "=" * 60)
        print("Done. All outputs are in output/")
        print("=" * 60)

    finally:
        _teardown_tee(_original_stdout, _log_file)
