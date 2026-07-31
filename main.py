"""
main.py
FastAPI backend for Chess Analytics.

Run with:
    uvicorn main:app --reload

API docs auto-generated at: http://localhost:8000/api/docs
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

import chess_data as cd
import chess_analysis as ca

app = FastAPI(title="Chess Analytics API", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load(username: str):
    """Load data for a user, raising clean HTTP errors for known failure modes."""
    try:
        return cd.get_data(username.lower())
    except Exception as e:
        msg = str(e)
        if "404" in msg or "not found" in msg.lower():
            raise HTTPException(404, detail=f"User '{username}' not found on Chess.com.")
        raise HTTPException(502, detail=f"Failed to fetch data from Chess.com: {msg}")


# ── Root ───────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


# ── Data endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/{username}/summary")
def summary(username: str):
    """Overall record: total, wins, losses, draws, win_rate."""
    games, _ = _load(username)
    return ca.overall_record(games)


@app.get("/api/{username}/charts/overview")
def charts_overview(username: str):
    """All charts for the Overview tab."""
    games, moves = _load(username)
    return {
        "rating_over_time": ca.fig_to_dict(ca.fig_rating_over_time(games)),
        "volatility":       ca.fig_to_dict(ca.fig_rating_volatility(games)),
        "termination":      ca.fig_to_dict(ca.fig_termination_breakdown(games)),
        "accuracy":         ca.fig_to_dict(ca.fig_accuracy_trend(games)),
    }


@app.get("/api/{username}/charts/openings")
def charts_openings(username: str, min_games: int = Query(5, ge=1, le=50)):
    """All charts for the Openings tab. min_games filters low-sample openings."""
    games, moves = _load(username)
    result = {
        "win_rate":   ca.fig_to_dict(ca.fig_win_rate_by_opening(games, min_games)),
        "repertoire": ca.fig_to_dict(ca.fig_opening_repertoire_treemap(games)),
    }
    if not moves.empty:
        result["phase"] = ca.fig_to_dict(ca.fig_phase_performance(moves, games))
    return result


@app.get("/api/{username}/charts/time")
def charts_time(username: str):
    """All charts for the Time tab."""
    games, moves = _load(username)
    result = {
        "time_class": ca.fig_to_dict(ca.fig_win_rate_by_time_class(games)),
        "heatmap":    ca.fig_to_dict(ca.fig_performance_heatmap(games)),
    }
    if not moves.empty:
        result["game_length"]    = ca.fig_to_dict(ca.fig_win_rate_by_game_length(moves, games))
        result["clock_pattern"]  = ca.fig_to_dict(ca.fig_clock_usage_pattern(moves))
        result["time_pressure"]  = ca.time_pressure_summary(moves)
    return result


@app.get("/api/{username}/charts/opponents")
def charts_opponents(username: str):
    """All charts/data for the Opponents tab."""
    games, moves = _load(username)
    result = {
        "rating_gap":    ca.fig_to_dict(ca.fig_win_rate_by_rating_gap(games)),
        "top_opponents": ca.top_opponents(games).reset_index().to_dict("records"),
        "opponent_list": sorted(games["opponent"].dropna().unique().tolist()),
    }
    if not moves.empty:
        result["comeback"] = ca.comeback_rate(moves, games)
    return result


@app.get("/api/{username}/h2h/{opponent}")
def h2h(username: str, opponent: str):
    """Head-to-head record against a specific opponent."""
    games, _ = _load(username)
    return ca.head_to_head(games, opponent)


@app.delete("/api/{username}/cache")
def clear_cache(username: str):
    """Clear cached data for a user, forcing a fresh fetch next request."""
    cd.clear_cache(username)
    return {"status": "cleared", "username": username}


# ── Static files (must be last) ────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")
