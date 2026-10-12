# Chess Profile Analysis

Type in a Chess.com username and get a breakdown of that player's games: results, openings, time use, and opponents. Everything runs in the browser using Chess.com's public API.

**Live site:** https://sahasreddye-sys.github.io/chess-profile-analysis/

![JavaScript](https://img.shields.io/badge/JavaScript-single%20file-F7DF1E?logo=javascript&logoColor=black)
![GitHub Pages](https://img.shields.io/badge/hosted%20on-GitHub%20Pages-222?logo=github)

## What it shows

- **Overview:** total games, wins, losses, win rate.
- **Openings:** results by opening, with a slider to hide openings played fewer than N times.
- **Time:** average time per move, moves played under time pressure.
- **Opponents:** most played opponents and head-to-head record against any of them, plus games where you were down material and comebacks.

## Run it locally

It is one file, `index.html`.

```bash
git clone https://github.com/sahasreddye-sys/chess-profile-analysis.git
cd chess-profile-analysis
python -m http.server 8000
```

Open http://localhost:8000 and enter a Chess.com username.

## Notes

- Data comes from `api.chess.com`, which only returns public games.
- Large accounts take longer because every monthly archive has to be fetched.
