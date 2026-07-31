"""
chess_data.py
Live data layer: fetches game archives from the Chess.com public API and parses
them into clean pandas DataFrames. Uses a thread-safe in-memory TTL cache
so repeated requests within 30 minutes don't re-hit the API.
"""

import io
import re
import time
import math
import requests
import chess
import chess.pgn
import pandas as pd
from threading import Lock

HEADERS = {
    "User-Agent": "chess-analytics-app/1.0 (contact: your_email@example.com)"
}

CLOCK_RE = re.compile(r"\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]")
CACHE_TTL_SECONDS = 1800  # 30 minutes

_cache: dict = {}
_cache_lock = Lock()


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
            return entry["data"]
        return None


def _cache_set(key, data):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def clear_cache(username: str = None):
    with _cache_lock:
        if username:
            keys = [k for k in _cache if k.startswith(username.lower() + ":")]
            for k in keys:
                del _cache[k]
        else:
            _cache.clear()


# ── Parsing helpers ────────────────────────────────────────────────────────────

def _clock_to_seconds(h, m, s) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def _piece_value(piece: chess.Piece) -> int:
    return {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
            chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}.get(piece.piece_type, 0)


def _material_balance(board: chess.Board) -> int:
    balance = 0
    for piece in board.piece_map().values():
        v = _piece_value(piece)
        balance += v if piece.color == chess.WHITE else -v
    return balance


# ── Fetch ──────────────────────────────────────────────────────────────────────

def get_archive_list(username: str) -> list:
    url = f"https://api.chess.com/pub/player/{username}/games/archives"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()["archives"]


def fetch_archive(url: str) -> list:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("games", [])


def fetch_all_raw_games(username: str) -> list:
    archives = get_archive_list(username)
    all_games = []
    for archive_url in archives:
        all_games.extend(fetch_archive(archive_url))
        time.sleep(0.3)
    return all_games


# ── Parse ──────────────────────────────────────────────────────────────────────

def parse_game(raw_game: dict, username: str):
    pgn_text = raw_game.get("pgn")
    if not pgn_text:
        return None, []

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None, []

    headers = game.headers
    is_white = raw_game.get("white", {}).get("username", "").lower() == username.lower()
    your_color = "white" if is_white else "black"
    your_side = raw_game.get("white" if is_white else "black", {})
    opp_side  = raw_game.get("black" if is_white else "white", {})

    your_result_raw = your_side.get("result")
    if your_result_raw == "win":
        result = "win"
    elif your_result_raw in ("checkmated", "timeout", "resigned", "lose", "abandoned"):
        result = "loss"
    else:
        result = "draw"

    acc_raw = raw_game.get("accuracies") or {}
    your_accuracy = acc_raw.get("white" if is_white else "black")

    utc_time = headers.get("UTCTime", "")
    hour = None
    if utc_time:
        try:
            hour = int(utc_time.split(":")[0])
        except ValueError:
            pass

    game_row = {
        "game_id":         raw_game.get("url", "").split("/")[-1],
        "url":             raw_game.get("url"),
        "date":            headers.get("UTCDate") or headers.get("Date"),
        "hour_utc":        hour,
        "your_color":      your_color,
        "your_rating":     your_side.get("rating"),
        "opponent":        opp_side.get("username"),
        "opponent_rating": opp_side.get("rating"),
        "result":          result,
        "termination":     headers.get("Termination"),
        "eco":             headers.get("ECO"),
        "opening_url":     headers.get("ECOUrl"),
        "time_control":    raw_game.get("time_control"),
        "time_class":      raw_game.get("time_class"),
        "rated":           raw_game.get("rated"),
        "your_accuracy":   your_accuracy,
        "rating_diff":     (your_side.get("rating") or 0) - (opp_side.get("rating") or 0),
    }

    move_rows = []
    board = game.board()
    node = game
    move_number = 0
    last_clock = {"white": None, "black": None}

    while node.variations:
        next_node = node.variations[0]
        move = next_node.move
        mover_color = "white" if board.turn == chess.WHITE else "black"
        move_san = board.san(move)
        board.push(move)
        move_number += 1

        comment = next_node.comment or ""
        m = CLOCK_RE.search(comment)
        clock_seconds = time_spent = None
        if m:
            clock_seconds = _clock_to_seconds(*m.groups())
            prev = last_clock[mover_color]
            if prev is not None:
                time_spent = prev - clock_seconds
            last_clock[mover_color] = clock_seconds

        bal = _material_balance(board)
        move_rows.append({
            "game_id":              game_row["game_id"],
            "move_number":          move_number,
            "mover_color":          mover_color,
            "is_your_move":         mover_color == your_color,
            "move_san":             move_san,
            "clock_seconds":        clock_seconds,
            "time_spent_seconds":   time_spent,
            "material_balance":     bal,
            "your_material_balance": bal if your_color == "white" else -bal,
        })
        node = next_node

    return game_row, move_rows


def parse_all_games(raw_games: list, username: str):
    games_rows, moves_rows = [], []
    for raw in raw_games:
        try:
            g, m = parse_game(raw, username)
        except Exception:
            continue
        if g is None:
            continue
        games_rows.append(g)
        moves_rows.extend(m)

    games_df = pd.DataFrame(games_rows)
    if not games_df.empty:
        games_df["date"] = pd.to_datetime(games_df["date"], format="%Y.%m.%d", errors="coerce")
        games_df["day_of_week"] = games_df["date"].dt.day_name()
        games_df = games_df.sort_values("date").reset_index(drop=True)

    return games_df, pd.DataFrame(moves_rows)


# ── Public API ─────────────────────────────────────────────────────────────────

def get_data(username: str):
    """Returns (games_df, moves_df), fetching live if not cached."""
    key = f"{username.lower()}:data"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    raw = fetch_all_raw_games(username.lower())
    result = parse_all_games(raw, username.lower())
    _cache_set(key, result)
    return result
