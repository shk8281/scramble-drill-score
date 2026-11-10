"""
src/build_site.py
-----------------
Build docs/index.html: one shareable page with every result, both charts and the
interactive scramble play viewer. GitHub Pages can serve the docs/ folder as-is.

Every number on the page is computed here from output/*.csv and output/results.txt
(written by main.py), so the page always matches the latest run.

Run from the project root after main.py:
    .venv\\Scripts\\python.exe -m src.build_site
"""

import base64
import json
import pathlib
import re
import sys

import numpy as np
import pandas as pd

try:
    from src.build_viewer import build_plays
except ImportError:  # running as a plain script
    from build_viewer import build_plays

ROOT = pathlib.Path(__file__).resolve().parent.parent


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def grab(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else "n/a"


def main() -> None:
    data_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
    out_dir = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "output"
    site_dir = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "docs"
    site_dir.mkdir(parents=True, exist_ok=True)

    t = pd.read_csv(out_dir / "targets.csv")
    r = pd.read_csv(out_dir / "receivers.csv")
    lb = pd.read_csv(out_dir / "leaderboard.csv").sort_values("avg_sep_gained", ascending=False)
    res = (out_dir / "results.txt").read_text(encoding="utf-8", errors="ignore")

    t["C"] = t.passResult == "C"
    hi, lo = t[t.sep_gained >= 1], t[t.sep_gained < 1]
    t["bucket"] = pd.cut(t.sep_gained, [-99, -1, 1, 3, 99],
                         labels=["Lost more than 1 yd", "-1 to +1 yd", "Gained 1 to 3 yds", "Gained more than 3 yds"])
    buckets = []
    for b, g in t.groupby("bucket", observed=True):
        k, n = int(g.C.sum()), len(g)
        a, z = wilson(k, n)
        buckets.append({"label": str(b), "n": n, "k": k, "pct": k / n, "lo": a, "hi": z})

    pos = []
    for p in ["WR", "TE", "RB"]:
        rr, tt = r[r.officialPosition == p], t[t.officialPosition == p]
        pos.append({"pos": p, "snaps": len(rr), "s0": rr.sep_start.mean(), "s1": rr.sep_throw.mean(),
                    "gain": rr.sep_gained.mean(), "targets": len(tt), "cmp": tt.C.mean(),
                    "share1": (tt.sep_gained >= 1).mean()})

    n_plays = int(grab(res, r"Plays kept\s*:\s*([\d,]+)").replace(",", "") or 0)
    pl = pd.read_csv(data_dir / "plays.csv")
    throws = int((pl.dropBackType.fillna("").str.contains("SCRAMBLE") & pl.passResult.isin(["C", "I", "IN"])).sum())
    stats = {
        "throws": throws,
        "plays": n_plays,
        "median": float(r.drop_duplicates(["gameId", "playId"]).scramble_duration_sec.median()),
        "named": grab(res, r"named target in desc\s*:\s*([\d,]+)"),
        "matched": len(t),
        "hiPct": hi.C.mean(), "hiK": int(hi.C.sum()), "hiN": len(hi),
        "loPct": lo.C.mean(), "loK": int(lo.C.sum()), "loN": len(lo),
        "p": grab(res, r"z-test \(two-sided\): z=[-\d.]+, p=([\d.]+)"),
        "odds": grab(res, r"Odds ratio\s*:\s*([\d.]+)"),
        "oddsP": grab(res, r"Odds ratio[\s\S]*?p-value\s*:\s*([\d.]+)"),
        "qualified": len(lb),
    }
    leaders = [{"name": x.displayName, "pos": x.officialPosition, "snaps": int(x.snaps), "gain": float(x.avg_sep_gained)}
               for x in lb.itertuples()]

    def img(name: str) -> str:
        return "data:image/png;base64," + base64.b64encode((out_dir / name).read_bytes()).decode()

    plays = build_plays(data_dir, out_dir)
    html = (pathlib.Path(__file__).parent / "site_template.html").read_text(encoding="utf-8")
    payload = {"stats": stats, "buckets": buckets, "positions": pos, "leaders": leaders}
    html = (html.replace("/*__DATA__*/{}", json.dumps(payload, separators=(",", ":")))
                .replace("/*__PLAYS__*/[]", json.dumps(plays, separators=(",", ":")))
                .replace("__IMG_PAYOFF__", img("separation_payoff.png"))
                .replace("__IMG_LEADERS__", img("leaderboard.png")))
    (site_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"Saved docs/index.html ({len(plays)} plays in the viewer)")


if __name__ == "__main__":
    main()
