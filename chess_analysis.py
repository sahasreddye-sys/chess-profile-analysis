"""
chess_analysis.py
All analysis functions and Plotly chart builders, grouped by dashboard tab.
Each function takes games_df / moves_df and returns a Plotly figure or a dict.
fig_to_dict() converts any figure to a JSON-safe dict for the API to return.
"""

import json
import math
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def fig_to_dict(fig) -> dict:
    """Convert a Plotly figure to a JSON-serializable dict."""
    return json.loads(fig.to_json())


def _safe(v):
    """Convert NaN/inf to None for JSON serialization."""
    if v is None:
        return None
    try:
        if math.isnan(v) or math.isinf(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# ── Overview ───────────────────────────────────────────────────────────────────

def overall_record(games: pd.DataFrame) -> dict:
    counts = games["result"].value_counts()
    total = len(games)
    return {
        "total":    total,
        "wins":     int(counts.get("win",  0)),
        "losses":   int(counts.get("loss", 0)),
        "draws":    int(counts.get("draw", 0)),
        "win_rate": round(counts.get("win", 0) / total, 4) if total else 0,
    }


def fig_rating_over_time(games: pd.DataFrame) -> go.Figure:
    df = games.dropna(subset=["your_rating"]).sort_values("date")
    return px.line(
        df, x="date", y="your_rating", color="time_class", markers=True,
        title="Rating Over Time",
        labels={"date": "Date", "your_rating": "Rating", "time_class": "Time Class"},
    )


def fig_rating_volatility(games: pd.DataFrame, window: int = 20) -> go.Figure:
    df = games.dropna(subset=["your_rating"]).sort_values("date").copy()
    df["rating_change"] = df["your_rating"].diff()
    df["rolling_volatility"] = df["rating_change"].rolling(window, min_periods=5).std()
    return px.line(
        df, x="date", y="rolling_volatility",
        title=f"Rating Volatility (rolling {window}-game std dev)",
        labels={"date": "Date", "rolling_volatility": "Volatility (pts)"},
    )


def fig_termination_breakdown(games: pd.DataFrame) -> go.Figure:
    df = games.copy()
    df["termination_clean"] = (
        df["termination"].fillna("unknown")
          .str.extract(r"(by .+)$", expand=False)
          .fillna(df["termination"])
    )
    counts = df.groupby(["result", "termination_clean"]).size().reset_index(name="count")
    fig = px.bar(
        counts, x="termination_clean", y="count", color="result",
        title="How Your Games End",
        labels={"termination_clean": "Termination Type", "count": "Games"},
        color_discrete_map={"win": "#22c55e", "loss": "#ef4444", "draw": "#f59e0b"},
    )
    fig.update_layout(xaxis_tickangle=-30)
    return fig


def fig_accuracy_trend(games: pd.DataFrame) -> go.Figure:
    df = games.dropna(subset=["your_accuracy"]).sort_values("date")
    if df.empty:
        return go.Figure().update_layout(
            title="No accuracy data available (only analyzed games include this)"
        )
    return px.scatter(
        df, x="date", y="your_accuracy", trendline="rolling",
        trendline_options=dict(window=10),
        title="Accuracy Trend Over Time (analyzed games only)",
        labels={"date": "Date", "your_accuracy": "Accuracy (%)"},
    )


# ── Openings ───────────────────────────────────────────────────────────────────

def win_rate_by_opening(games: pd.DataFrame, min_games: int = 5) -> pd.DataFrame:
    grouped = games.groupby("eco")["result"].value_counts().unstack(fill_value=0)
    for col in ["win", "loss", "draw"]:
        if col not in grouped.columns:
            grouped[col] = 0
    grouped["total"]    = grouped[["win", "loss", "draw"]].sum(axis=1)
    grouped["win_rate"] = grouped["win"] / grouped["total"]
    return grouped[grouped["total"] >= min_games].sort_values("win_rate", ascending=False)


def fig_win_rate_by_opening(games: pd.DataFrame, min_games: int = 5) -> go.Figure:
    df = win_rate_by_opening(games, min_games).reset_index()
    fig = px.bar(
        df, x="win_rate", y="eco", orientation="h",
        title=f"Win Rate by Opening (min {min_games} games)",
        labels={"win_rate": "Win Rate", "eco": "ECO Code"},
        hover_data=["total", "win", "loss", "draw"],
        color="win_rate", color_continuous_scale="RdYlGn", range_color=[0, 1],
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
    return fig


def fig_opening_repertoire_treemap(games: pd.DataFrame) -> go.Figure:
    df = games.dropna(subset=["eco"]).copy()
    grouped = df.groupby(["your_color", "eco"]).agg(
        games=("result", "count"),
        win_rate=("result", lambda s: (s == "win").mean()),
    ).reset_index()
    return px.treemap(
        grouped, path=["your_color", "eco"], values="games", color="win_rate",
        color_continuous_scale="RdYlGn", range_color=[0, 1],
        title="Opening Repertoire (size = frequency, color = win rate)",
    )


def fig_phase_performance(moves: pd.DataFrame, games: pd.DataFrame) -> go.Figure:
    lengths = moves.groupby("game_id")["move_number"].max().reset_index(name="final_move")
    lengths["phase"] = lengths["final_move"].apply(
        lambda n: "Opening (≤15)" if n <= 15 else ("Middlegame (16–35)" if n <= 35 else "Endgame (36+)")
    )
    merged = games.merge(lengths, on="game_id", how="inner")
    grouped = (
        merged.groupby("phase")["result"]
              .value_counts(normalize=True).unstack(fill_value=0).reset_index()
    )
    if "win" not in grouped.columns:
        grouped["win"] = 0
    return px.bar(
        grouped, x="phase", y="win",
        title="Win Rate by Game Phase (when the game ended)",
        labels={"phase": "Phase", "win": "Win Rate"},
        category_orders={"phase": ["Opening (≤15)", "Middlegame (16–35)", "Endgame (36+)"]},
        color="win", color_continuous_scale="RdYlGn", range_color=[0, 1],
    )


# ── Time ───────────────────────────────────────────────────────────────────────

def fig_win_rate_by_time_class(games: pd.DataFrame) -> go.Figure:
    grouped = (
        games.groupby("time_class")["result"]
             .value_counts(normalize=True).unstack(fill_value=0).reset_index()
    )
    if "win" not in grouped.columns:
        grouped["win"] = 0
    return px.bar(
        grouped, x="time_class", y="win",
        title="Win Rate by Time Control",
        labels={"time_class": "Time Class", "win": "Win Rate"},
        color="win", color_continuous_scale="RdYlGn", range_color=[0, 1],
    )


def fig_win_rate_by_game_length(moves: pd.DataFrame, games: pd.DataFrame, bin_size: int = 10) -> go.Figure:
    lengths = moves.groupby("game_id")["move_number"].max().reset_index(name="total_moves")
    merged = games.merge(lengths, on="game_id", how="inner")
    merged["length_bucket"] = (merged["total_moves"] // bin_size) * bin_size
    grouped = (
        merged.groupby("length_bucket")["result"]
              .value_counts(normalize=True).unstack(fill_value=0).reset_index()
    )
    if "win" not in grouped.columns:
        grouped["win"] = 0
    return px.bar(
        grouped, x="length_bucket", y="win",
        title=f"Win Rate by Game Length (every {bin_size} moves)",
        labels={"length_bucket": "Total Moves", "win": "Win Rate"},
        color="win", color_continuous_scale="RdYlGn", range_color=[0, 1],
    )


def time_pressure_summary(moves: pd.DataFrame, threshold: int = 30) -> dict:
    your = moves[moves["is_your_move"] & moves["time_spent_seconds"].notna()]
    under = your[your["clock_seconds"] < threshold]
    normal = your[your["clock_seconds"] >= threshold]
    return {
        "avg_time_under_pressure": _safe(under["time_spent_seconds"].mean()),
        "avg_time_normal":         _safe(normal["time_spent_seconds"].mean()),
        "moves_under_pressure":    len(under),
        "moves_normal":            len(normal),
    }


def fig_clock_usage_pattern(moves: pd.DataFrame) -> go.Figure:
    your = moves[moves["is_your_move"] & moves["clock_seconds"].notna()]
    avg  = your.groupby("move_number")["clock_seconds"].mean().reset_index()
    return px.line(
        avg, x="move_number", y="clock_seconds",
        title="Average Clock Time Remaining by Move Number",
        labels={"move_number": "Move Number", "clock_seconds": "Avg Seconds Remaining"},
    )


def fig_performance_heatmap(games: pd.DataFrame) -> go.Figure:
    df = games.dropna(subset=["hour_utc", "day_of_week"]).copy()
    if df.empty:
        return go.Figure().update_layout(title="No time-of-day data available")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    df["is_win"] = (df["result"] == "win").astype(int)
    pivot = df.pivot_table(index="day_of_week", columns="hour_utc", values="is_win", aggfunc="mean")
    pivot = pivot.reindex(day_order)
    return px.imshow(
        pivot, color_continuous_scale="RdYlGn", aspect="auto",
        labels=dict(x="Hour (UTC)", y="Day of Week", color="Win Rate"),
        title="Performance Heatmap: Win Rate by Day & Hour (UTC)",
    )


# ── Opponents ──────────────────────────────────────────────────────────────────

def fig_win_rate_by_rating_gap(games: pd.DataFrame, bin_size: int = 50) -> go.Figure:
    df = games.copy()
    df["gap_bucket"] = (df["rating_diff"] // bin_size) * bin_size
    grouped = (
        df.groupby("gap_bucket")["result"]
          .value_counts(normalize=True).unstack(fill_value=0).reset_index()
    )
    if "win" not in grouped.columns:
        grouped["win"] = 0
    return px.bar(
        grouped, x="gap_bucket", y="win",
        title="Win Rate vs. Rating Gap (you − opponent)",
        labels={"gap_bucket": "Rating Gap", "win": "Win Rate"},
        color="win", color_continuous_scale="RdYlGn", range_color=[0, 1],
    )


def top_opponents(games: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    grouped = games.groupby("opponent")["result"].value_counts().unstack(fill_value=0)
    for col in ["win", "loss", "draw"]:
        if col not in grouped.columns:
            grouped[col] = 0
    grouped["total"]    = grouped[["win", "loss", "draw"]].sum(axis=1)
    grouped["win_rate"] = (grouped["win"] / grouped["total"]).round(3)
    return grouped.sort_values("total", ascending=False).head(n)


def head_to_head(games: pd.DataFrame, opponent: str) -> dict:
    df = games[games["opponent"].str.lower() == opponent.lower()]
    counts = df["result"].value_counts()
    return {
        "wins":   int(counts.get("win",  0)),
        "losses": int(counts.get("loss", 0)),
        "draws":  int(counts.get("draw", 0)),
        "games":  df[["date", "your_color", "result", "time_class", "url"]]
                    .sort_values("date", ascending=False)
                    .assign(date=lambda d: d["date"].astype(str))
                    .to_dict("records"),
    }


def comeback_rate(moves: pd.DataFrame, games: pd.DataFrame, threshold: int = 3) -> dict:
    down = moves[moves["your_material_balance"] <= -threshold]["game_id"].unique()
    if len(down) == 0:
        return {"games_down": 0, "comeback_wins": 0, "comeback_rate": None}
    rel  = games[games["game_id"].isin(down)]
    wins = int((rel["result"] == "win").sum())
    return {
        "games_down":    len(down),
        "comeback_wins": wins,
        "comeback_rate": _safe(wins / len(down)),
    }
