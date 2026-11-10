---
inclusion: always
---

# Scramble Drill Score — Project Rules

## Project

This is an NFL Big Data Bowl entry. The central question: when the QB scrambles, does it pay for receivers to keep working to get open? Primary audience is coaches; secondary audience is broadcasters.

## Data

Data lives in `data/`:
- `plays.csv` — play-level metadata and outcomes
- `pffScoutingData.csv` — PFF role and grade data
- `players.csv` — player metadata
- `games.csv` — game metadata
- `tracking/tracking_<gameId>.csv` — player tracking at 10 frames/sec

Column documentation is in `DATA_README.md`.

Never commit `data/`. It is gitignored.

## Running Python

Always invoke Python as `.venv\Scripts\python.exe` (Windows, PowerShell). Python is not on PATH.

## PFF Roles

PFF roles are capitalized exactly as they appear in the data:
- `"Pass"` — quarterback
- `"Pass Route"` — receivers
- `"Coverage"` — defenders
- `"Pass Block"` — offensive linemen
- `"Pass Rush"` — pass rushers

## Tracking Data Conventions

- Ball rows in tracking have `nflId` missing; drop them before any player-level analysis.
- **Snap**: first frame where `event` is in `["ball_snap", "autoevent_ballsnap"]`.
- **Throw**: first frame where `event` is in `["pass_forward", "autoevent_passforward"]`.
- Events can repeat across frames; always take the first occurrence.
- Tracking ends 0.5 s after the throw. Play outcomes come from `plays.csv`, never from tracking.

## Project Structure

- Source code lives in `src/`.
- Entry point is `main.py` at the workspace root.
- Outputs (charts, tables, reports) go to `output/`.

## Writing and Communication

- Use plain language in all charts, comments, and the README.
- No em dashes. Use a comma or rewrite the sentence instead.
- Say "associated with", not "causes". This is observational data.
