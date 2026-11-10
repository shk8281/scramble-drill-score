"""
src/build_viewer.py
-------------------
Build output/play_viewer.html: an interactive, self-contained page that replays
scramble plays from the tracking data. Drag the timeline to scrub through a play,
click any receiver to track his separation, hover a dot to see who it is.

Run from the project root after main.py:
    .venv\\Scripts\\python.exe -m src.build_viewer
"""

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"

SNAP = {"ball_snap", "autoevent_ballsnap"}
THROW = {"pass_forward", "autoevent_passforward"}
N_GOOD, N_BAD = 16, 10   # plays where the target gained the most / lost the most


def to_xy(df: pd.DataFrame) -> list:
    """Positions as integer tenths of a yard; -1 where a player has no row that frame."""
    a = np.round(df[["x", "y"]].to_numpy(dtype=float) * 10)
    return np.where(np.isnan(a), -1, a).astype(int).tolist()


def pick_plays(targets: pd.DataFrame, leaders: list[str]) -> pd.DataFrame:
    t = targets.copy()
    good = t[t.passResult == "C"].nlargest(N_GOOD, "sep_gained")
    bad = t.nsmallest(N_BAD, "sep_gained")
    lead = t[t.displayName.isin(leaders)].sort_values("sep_gained", ascending=False).groupby("displayName").head(2)
    picks = pd.concat([lead, good, bad]).drop_duplicates(["gameId", "playId"])
    return picks.sort_values("sep_gained", ascending=False)


def build_plays(data_dir: pathlib.Path, out_dir: pathlib.Path) -> list[dict]:
    """Tracking frames for the selected scramble plays, field-normalized so offense moves left to right."""
    targets = pd.read_csv(out_dir / "targets.csv")
    leaders = pd.read_csv(out_dir / "leaderboard.csv").sort_values("avg_sep_gained", ascending=False).displayName.head(5).tolist()
    plays = pd.read_csv(data_dir / "plays.csv")
    games = pd.read_csv(data_dir / "games.csv")
    players = pd.read_csv(data_dir / "players.csv")[["nflId", "displayName", "officialPosition"]]
    pff = pd.read_csv(data_dir / "pffScoutingData.csv")[["gameId", "playId", "nflId", "pff_role"]]

    picks = pick_plays(targets, leaders).merge(
        plays[["gameId", "playId", "possessionTeam", "defensiveTeam", "quarter", "down", "yardsToGo", "absoluteYardlineNumber"]],
        on=["gameId", "playId"]).merge(games[["gameId", "week"]], on="gameId")

    out = []
    for gid, grp in picks.groupby("gameId"):
        trk = pd.read_csv(data_dir / "tracking" / f"tracking_{gid}.csv")
        for _, p in grp.iterrows():
            d = trk[trk.playId == p.playId].copy()
            if d.empty:
                continue
            ev = d.drop_duplicates("frameId").set_index("frameId").event
            snap = int(ev[ev.isin(SNAP)].index.min())
            throw = int(ev[ev.isin(THROW)].index.min())
            flip = d.playDirection.iloc[0] == "left"
            if flip:
                d["x"] = 120 - d.x
                d["y"] = 53.3 - d.y
            d = d[d.frameId >= snap - 10]
            frames = sorted(d.frameId.unique())
            roles = pff[(pff.gameId == gid) & (pff.playId == p.playId)].set_index("nflId").pff_role
            qb_id = int(roles[roles == "Pass"].index[0])
            qb = d[d.nflId == qb_id].set_index("frameId")
            y0 = qb.y.get(snap)
            mv = qb.loc[snap:throw]
            mv = mv[(mv.y - y0).abs() > 3]
            start = int(mv.index.min())

            ppl = []
            for nid, pdf in d[d.nflId.notna()].groupby("nflId"):
                nid = int(nid)
                info = players[players.nflId == nid]
                pos = pdf.set_index("frameId").reindex(frames)
                ppl.append({
                    "id": nid,
                    "n": info.displayName.iloc[0] if len(info) else str(nid),
                    "pos": info.officialPosition.iloc[0] if len(info) else "",
                    "j": int(pdf.jerseyNumber.iloc[0]) if pdf.jerseyNumber.notna().any() else 0,
                    "o": bool(pdf.team.iloc[0] == p.possessionTeam),
                    "r": roles.get(nid, ""),
                    "xy": to_xy(pos),
                })
            ball = d[d.nflId.isna()].set_index("frameId").reindex(frames)
            los = p.absoluteYardlineNumber if not flip else 120 - p.absoluteYardlineNumber
            out.append({
                "key": f"{gid}-{p.playId}",
                "title": f"{p.displayName} ({p.officialPosition}), {p.possessionTeam} vs {p.defensiveTeam}, Wk {p.week}",
                "desc": p.playDescription,
                "result": {"C": "Complete", "I": "Incomplete", "IN": "Intercepted"}[p.passResult],
                "q": int(p.quarter), "down": int(p.down), "togo": int(p.yardsToGo),
                "los": round(float(los), 1),
                "target": int(p.nflId), "qb": qb_id,
                "sepStart": round(float(p.sep_start), 2), "sepThrow": round(float(p.sep_throw), 2), "gained": round(float(p.sep_gained), 2),
                "f0": int(frames[0]), "snap": snap, "start": start, "throw": throw,
                "players": ppl,
                "ball": to_xy(ball),
            })
    out.sort(key=lambda r: -r["gained"])
    return out


def main() -> None:
    data_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DATA
    out_dir = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    out = build_plays(data_dir, out_dir)
    html = (pathlib.Path(__file__).parent / "viewer_template.html").read_text(encoding="utf-8")
    html = html.replace("/*__PLAYS__*/[]", json.dumps(out, separators=(",", ":")))
    (out_dir / "play_viewer.html").write_text(html, encoding="utf-8")
    print(f"Saved output/play_viewer.html with {len(out)} scramble plays")


if __name__ == "__main__":
    main()
