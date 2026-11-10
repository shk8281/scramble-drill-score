"""
src/charts.py
-------------
Charts and statistical summaries for the scramble-drill-score project.

headline_chart(targets)
    Bar chart: completion % by sep_gained bucket for targeted receivers,
    Wilson 95% CI error bars, completion % label on each bar.
    Two-sided two-proportion z-test and logistic regression printed.
    Saves output/separation_payoff.png.

leaderboard(receivers)
    Horizontal bar chart: average sep_gained per receiver (min 12 snaps),
    coloured by officialPosition.
    Saves output/leaderboard.png and output/leaderboard.csv.
"""

import math
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportions_ztest
import statsmodels.formula.api as smf

from src.target import build_targets

OUTPUT_DIR = pathlib.Path(__file__).parent.parent / "output"
TARGETS_CSV   = OUTPUT_DIR / "targets.csv"
RECEIVERS_CSV = OUTPUT_DIR / "receivers.csv"
CHART_PATH    = OUTPUT_DIR / "separation_payoff.png"
LEADER_PNG    = OUTPUT_DIR / "leaderboard.png"
LEADER_CSV    = OUTPUT_DIR / "leaderboard.csv"

BUCKET_EDGES  = [-np.inf, -1.0, 1.0, 3.0, np.inf]
BUCKET_LABELS = ["< -1 yd", "-1 to 1 yd", "1 to 3 yds", "> 3 yds"]

MIN_SNAPS = 12


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _wilson_ci(n_success: int, n_total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. Returns (lower, upper) as proportions."""
    if n_total == 0:
        return 0.0, 0.0
    p_hat = n_success / n_total
    denom = 1 + z**2 / n_total
    centre = (p_hat + z**2 / (2 * n_total)) / denom
    half = (z / denom) * math.sqrt(
        p_hat * (1 - p_hat) / n_total + z**2 / (4 * n_total**2)
    )
    return max(0.0, centre - half), min(1.0, centre + half)


# ---------------------------------------------------------------------------
# headline_chart
# ---------------------------------------------------------------------------

def headline_chart(targets: pd.DataFrame | None = None) -> None:
    """
    Bar chart of completion % by sep_gained bucket.
    Prints two-sided z-test and logistic regression results.
    Saves output/separation_payoff.png.
    """
    if targets is None:
        targets = pd.read_csv(TARGETS_CSV)

    df = targets.copy()
    df["completed"] = (df["passResult"] == "C").astype(int)

    df["bucket"] = pd.cut(
        df["sep_gained"], bins=BUCKET_EDGES, labels=BUCKET_LABELS, right=False
    )

    # Per-bucket stats.
    rows = []
    for label in BUCKET_LABELS:
        sub = df[df["bucket"] == label]
        n = len(sub)
        k = int(sub["completed"].sum())
        p = k / n if n > 0 else 0.0
        lo, hi = _wilson_ci(k, n)
        rows.append({"bucket": label, "n": n, "k": k, "p": p, "lo": lo, "hi": hi})
    stats = pd.DataFrame(rows)

    # --- two-sided z-test: sep_gained >= 1 vs < 1 ---
    pos = df[df["sep_gained"] >= 1.0]
    neg = df[df["sep_gained"] <  1.0]
    n1, k1 = len(pos), int(pos["completed"].sum())
    n2, k2 = len(neg), int(neg["completed"].sum())
    p1 = k1 / n1 if n1 > 0 else float("nan")
    p2 = k2 / n2 if n2 > 0 else float("nan")

    print("\nTwo-group completion rates")
    print(f"  sep_gained >= 1 yd : {p1:.1%}  (n={n1:,}, completions={k1:,})")
    print(f"  sep_gained <  1 yd : {p2:.1%}  (n={n2:,}, completions={k2:,})")
    if n1 > 0 and n2 > 0:
        stat, pval = proportions_ztest(
            count=[k1, k2], nobs=[n1, n2], alternative="two-sided"
        )
        print(f"  Two-proportion z-test (two-sided): z={stat:.3f}, p={pval:.4f}")
    else:
        print("  Not enough data for z-test.")

    # --- logistic regression ---
    print("\nLogistic regression: completion ~ sep_gained + sep_start + C(officialPosition)")
    reg_df = df[["completed", "sep_gained", "sep_start", "officialPosition"]].dropna()
    pos_counts = reg_df["officialPosition"].value_counts()
    keep_pos = pos_counts[pos_counts >= 5].index
    reg_df = reg_df[reg_df["officialPosition"].isin(keep_pos)].copy()
    try:
        model = smf.logit(
            "completed ~ sep_gained + sep_start + C(officialPosition)",
            data=reg_df,
        ).fit(disp=False)
        coef      = model.params["sep_gained"]
        pval_reg  = model.pvalues["sep_gained"]
        odds_ratio = math.exp(coef)
        print(f"  sep_gained coef  : {coef:+.4f}")
        print(f"  Odds ratio       : {odds_ratio:.4f}")
        print(f"  p-value          : {pval_reg:.4f}")
    except Exception as exc:
        print(f"  Logistic regression failed: {exc}")

    # --- chart ---
    # Extra top margin so title + subtitle do not overlap the bars.
    fig, ax = plt.subplots(figsize=(9, 6.8))
    fig.subplots_adjust(top=0.80)   # reserve ~20% of figure height above axes

    x = np.arange(len(BUCKET_LABELS))
    bar_width = 0.55
    colours = ["#c0392b", "#95a5a6", "#2980b9", "#1a5276"]

    bars = ax.bar(
        x, stats["p"] * 100, width=bar_width,
        color=colours, alpha=0.88, zorder=3,
    )

    # Wilson CI error bars -- clip to 0 so yerr is never negative.
    err_lo = ((stats["p"] - stats["lo"]) * 100).clip(lower=0)
    err_hi = ((stats["hi"] - stats["p"]) * 100).clip(lower=0)
    ax.errorbar(
        x, stats["p"] * 100,
        yerr=[err_lo.values, err_hi.values],
        fmt="none", color="#2c3e50",
        capsize=5, capthick=1.8, linewidth=1.8, zorder=4,
    )

    # Completion % label inside (or on top of) each bar.
    for bar, row in zip(bars, stats.itertuples()):
        bar_top = row.p * 100
        label   = f"{row.p:.0%}"
        # Place inside bar if tall enough, otherwise just above it.
        if bar_top >= 12:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar_top / 2,
                label,
                ha="center", va="center",
                fontsize=12, fontweight="bold", color="white",
                zorder=5,
            )
        else:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar_top + 1.5,
                label,
                ha="center", va="bottom",
                fontsize=12, fontweight="bold", color="#2c3e50",
                zorder=5,
            )
        # n= label above the CI whisker.
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            min(row.hi * 100 + 2.0, 98),
            f"n={row.n:,}",
            ha="center", va="bottom", fontsize=10, color="#2c3e50",
        )

    # Overall reference line -- label on the LEFT side.
    overall_p = df["completed"].mean() * 100
    ax.axhline(overall_p, color="#7f8c8d", linewidth=1.2, linestyle="--", zorder=2)
    ax.text(
        -0.42,                 # just left of the first bar
        overall_p + 0.8,
        f"Overall\n{overall_p:.1f}%",
        ha="left", va="bottom", fontsize=9, color="#7f8c8d",
    )

    # Title and subtitle -- placed in figure coordinates so they always
    # have room above the axes.
    fig.text(
        0.08, 0.95,
        "Receivers who keep working on scrambles get caught more often",
        fontsize=14, fontweight="bold", ha="left", va="top",
        transform=fig.transFigure,
    )
    fig.text(
        0.08, 0.875,
        "2021 NFL weeks 1-8  |  scramble throws with a named target",
        fontsize=10.5, color="#555555", ha="left", va="top",
        transform=fig.transFigure,
    )

    ax.set_xlabel("Separation gained during QB scramble (yards)", fontsize=12, labelpad=8)
    ax.set_ylabel("Completion %", fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(BUCKET_LABELS, fontsize=12)
    ax.set_xlim(-0.6, len(BUCKET_LABELS) - 0.4)
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))
    ax.tick_params(labelsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=1)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHART_PATH, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved output/separation_payoff.png")


# ---------------------------------------------------------------------------
# leaderboard
# ---------------------------------------------------------------------------

# Colour palette for positions (extend if new positions appear).
_POS_COLOURS = {
    "WR": "#2980b9",
    "TE": "#27ae60",
    "RB": "#e67e22",
    "FB": "#8e44ad",
    "HB": "#e67e22",   # treat HB same as RB
    "QB": "#7f8c8d",
}
_DEFAULT_COLOUR = "#95a5a6"


def leaderboard(receivers: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Horizontal bar chart of average sep_gained per receiver (min 12 snaps).

    Parameters
    ----------
    receivers : pd.DataFrame or None
        If None, reads output/receivers.csv.

    Returns
    -------
    pd.DataFrame  -- the qualified leaderboard data (also saved to CSV).
    """
    if receivers is None:
        receivers = pd.read_csv(RECEIVERS_CSV)

    # Snap count = number of plays a receiver appears in.
    snap_counts = (
        receivers.groupby(["nflId", "displayName", "officialPosition"])
        .agg(snaps=("playId", "count"), avg_sep_gained=("sep_gained", "mean"))
        .reset_index()
    )

    qualified = snap_counts[snap_counts["snaps"] >= MIN_SNAPS].copy()
    n_qualified = len(qualified)
    print(f"\nLeaderboard: {n_qualified:,} receivers with >= {MIN_SNAPS} scramble snaps")

    # Top 10 and bottom 5.
    qualified = qualified.sort_values("avg_sep_gained", ascending=False).reset_index(drop=True)
    top10   = qualified.head(10)
    bottom5 = qualified.tail(5)
    board   = pd.concat([top10, bottom5], ignore_index=True)

    # Save CSV (full qualified list).
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    qualified.to_csv(LEADER_CSV, index=False)
    print(f"  Saved output/leaderboard.csv ({n_qualified} rows)")

    # --- chart ---
    n_bars = len(board)
    fig_height = max(6, 0.50 * n_bars + 2.2)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    # Tighten gap between subtitle and plot by reducing top padding.
    fig.subplots_adjust(top=0.88, left=0.28, right=0.95, bottom=0.08)

    # Insert a visual gap between top-10 and bottom-5.
    # Rows 0-9 are the top 10; rows 10-14 are the bottom 5.
    # We shift the bottom-5 bars down by an extra 0.8 units to create space.
    GAP = 0.9
    y_positions = np.array(
        [float(i) for i in range(10)] +
        [10.0 + GAP + float(i) for i in range(len(board) - 10)]
    )

    bar_colours = [
        _POS_COLOURS.get(str(pos).upper(), _DEFAULT_COLOUR)
        for pos in board["officialPosition"]
    ]

    ax.barh(
        y_positions, board["avg_sep_gained"],
        color=bar_colours, alpha=0.88,
        height=0.65, zorder=3,
    )

    # Snap count labels.
    # Positive bars: label just past the right end, dark text.
    # Negative bars: label just inside the bar near the zero line, white text.
    for i, row in enumerate(board.itertuples()):
        val = row.avg_sep_gained
        yp  = y_positions[i]
        if val >= 0:
            ax.text(
                val + 0.03, yp,
                f"{row.snaps} snaps",
                ha="left", va="center", fontsize=8.5, color="#2c3e50",
            )
        else:
            # Place inside the bar, close to the zero line.
            ax.text(
                -0.04, yp,
                f"{row.snaps} snaps",
                ha="right", va="center", fontsize=8.5, color="white",
                fontweight="bold",
            )

    # Dashed divider between top-10 and bottom-5.
    divider_y = 9.5 + GAP / 2
    ax.axhline(divider_y, color="#aaaaaa", linewidth=1.0,
               linestyle="--", zorder=2)

    # Section labels in data coordinates.
    # x_right: just inside the right edge of the plot area.
    x_right = ax.get_xlim()[1] - 0.02 * (ax.get_xlim()[1] - ax.get_xlim()[0])
    # "Top 10": just above the first bar (y=0 when inverted means top).
    ax.text(
        x_right, -0.55,
        "Top 10",
        ha="right", va="top", fontsize=8, color="#888888", style="italic",
    )
    # "Bottom 5": just below the divider line.
    ax.text(
        x_right, divider_y + 0.1,
        "Bottom 5",
        ha="right", va="top", fontsize=8, color="#888888", style="italic",
    )

    # Vertical line at 0.
    ax.axvline(0, color="#2c3e50", linewidth=1.0, zorder=2)

    # Player name labels on y-axis.
    ax.set_yticks(y_positions)
    ax.set_yticklabels(board["displayName"], fontsize=10)
    ax.invert_yaxis()   # best at top

    # Legend for positions.
    seen_positions = board["officialPosition"].unique()
    legend_handles = [
        plt.Rectangle(
            (0, 0), 1, 1,
            color=_POS_COLOURS.get(str(p).upper(), _DEFAULT_COLOUR),
            alpha=0.88,
        )
        for p in seen_positions
    ]
    ax.legend(
        legend_handles, seen_positions,
        title="Position", fontsize=9, title_fontsize=9,
        loc="lower right", framealpha=0.9,
    )

    # Titles placed close together just above the axes.
    fig.text(
        0.02, 0.975,
        "Who gets open when the play breaks down",
        fontsize=13, fontweight="bold", ha="left", va="top",
        transform=fig.transFigure,
    )
    fig.text(
        0.02, 0.930,
        f"Average separation gained during QB scrambles, "
        f"min. {MIN_SNAPS} snaps, 2021 weeks 1-8",
        fontsize=10, color="#555555", ha="left", va="top",
        transform=fig.transFigure,
    )

    ax.set_xlabel("Average separation gained (yards)", fontsize=11)
    ax.grid(axis="x", linestyle="--", alpha=0.4, zorder=1)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.savefig(LEADER_PNG, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved output/leaderboard.png")

    return qualified


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    targets   = build_targets()
    headline_chart(targets)
    leaderboard()
