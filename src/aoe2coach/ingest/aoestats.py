"""Ingesta de aoestats.io — la fuente de win rates por civ, mapa y matchup.

Usamos la API de agregados (`/api/stats/`), no los dumps Parquet: con 6,7 MB cubre lo que el
motor necesita y evita reprocesar millones de partidas. Los dumps se usan aparte, sólo para el
corpus histórico de uptimes (ver `dumps.py`).

Detalle verificado el 17-ago-2026: aunque se pida un `elo_grouping` puntual, la respuesta trae
las 6 filas (all + los 5 tramos). Con una sola descarga por patch alcanza.
"""

from __future__ import annotations

from typing import Any, Iterator

from aoe2coach.config import AOESTATS_PATCHES, AOESTATS_STATS, DATA_PATCH
from aoe2coach.ingest.http import fetch_json, meta_of

#: aoestats usa -1.0 como centinela cuando no pudo calcular el intervalo.
CI_SENTINEL = -1.0


def _fname(patch: int) -> str:
    return f"aoestats_stats_{patch}.json"


def download(patch: int = DATA_PATCH, *, force: bool = False) -> list[dict]:
    return fetch_json(
        AOESTATS_STATS,
        _fname(patch),
        force=force,
        params={"patch": patch, "grouping": "random_map", "elo_grouping": "all"},
    )


def download_patches(*, force: bool = False) -> list[dict]:
    return fetch_json(AOESTATS_PATCHES, "aoestats_patches.json", force=force)


def source_of(patch: int = DATA_PATCH) -> tuple[str, str]:
    m = meta_of(_fname(patch))
    return m.get("url") or AOESTATS_STATS, m.get("fetched_at") or ""


def _valid(node: dict) -> bool:
    """Descarta las entradas vacías (n=0 y centinela -1.0) en vez de propagar ceros falsos."""
    return bool(node) and node.get("num_games", 0) > 0 and node.get("ci_lower") != CI_SENTINEL


def _base(patch: int, elo: str, node: dict) -> dict:
    return {
        "patch": patch,
        "elo_bucket": elo,
        "n": int(node["num_games"]),
        "wins": int(node["wins"]),
        "play_rate": node.get("play_rate"),
        # win_rate / ci se recalculan con Wilson en la capa transform; guardamos el original
        # para poder contrastar.
        "src_win_rate": node.get("win_rate"),
        "src_ci_low": node.get("ci_lower"),
        "src_ci_high": node.get("ci_upper"),
    }


def rows_civ_performance(payload: list[dict], patch: int = DATA_PATCH) -> Iterator[dict]:
    """Una fila por (patch, elo, mapa, civ). `map = 'all'` es el agregado de todos los mapas."""
    for block in payload:
        elo = block["elo_grouping"]
        for civ, node in block["civ_stats"].items():
            if _valid(node):
                yield {
                    **_base(patch, elo, node),
                    "map": "all",
                    "civ": civ,
                    "rank": node.get("rank"),
                    "prior_rank": node.get("prior_rank"),
                    "avg_game_length": node.get("avg_game_length"),
                }
            for map_name, mnode in (node.get("by_map") or {}).items():
                if _valid(mnode):
                    yield {
                        **_base(patch, elo, mnode),
                        "map": map_name,
                        "civ": civ,
                        "rank": None,
                        "prior_rank": None,
                        "avg_game_length": None,
                    }


def rows_matchup(payload: list[dict], patch: int = DATA_PATCH) -> Iterator[dict]:
    """Civ vs civ. Ojo: aoestats no lo desglosa por mapa, es agregado de todos los mapas."""
    for block in payload:
        elo = block["elo_grouping"]
        for civ, node in block["civ_stats"].items():
            for opp, mnode in (node.get("by_matchup") or {}).items():
                if _valid(mnode):
                    yield {**_base(patch, elo, mnode), "civ": civ, "opp_civ": opp}


def rows_by_duration(payload: list[dict], patch: int = DATA_PATCH) -> Iterator[dict]:
    """Win rate por duración de partida: el proxy de si una civ es de early o de late game."""
    for block in payload:
        elo = block["elo_grouping"]
        for civ, node in block["civ_stats"].items():
            for bucket, dnode in (node.get("by_game_time") or {}).items():
                if _valid(dnode):
                    yield {**_base(patch, elo, dnode), "civ": civ, "duration_bucket": bucket}


def rows_map(payload: list[dict], patch: int = DATA_PATCH) -> Iterator[dict]:
    """Play rate de cada mapa. `num_games` acá cuenta partidas, no jugadores."""
    for block in payload:
        elo = block["elo_grouping"]
        for map_name, node in (block.get("map_stats") or {}).items():
            if node.get("num_games", 0) > 0:
                yield {
                    "patch": patch,
                    "elo_bucket": elo,
                    "map": map_name,
                    "n": int(node["num_games"]),
                    "play_rate": node.get("play_rate"),
                }


def totals(payload: list[dict], patch: int = DATA_PATCH) -> Iterator[dict]:
    for block in payload:
        yield {
            "patch": patch,
            "elo_bucket": block["elo_grouping"],
            "grouping": block["grouping"],
            "total_games": block["total_games"],
        }


def summary(payload: list[dict]) -> dict[str, Any]:
    return {
        "bloques": len(payload),
        "elo_buckets": [b["elo_grouping"] for b in payload],
        "civs": len(payload[0]["civ_stats"]) if payload else 0,
        "mapas": len(payload[0].get("map_stats") or {}) if payload else 0,
        "total_games_all": next(
            (b["total_games"] for b in payload if b["elo_grouping"] == "all"), None
        ),
    }
