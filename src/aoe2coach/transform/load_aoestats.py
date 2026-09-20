"""Carga de aoestats a las tablas `mart_*`, recalculando la estadística con Wilson."""

from __future__ import annotations

import duckdb

from aoe2coach.config import DATA_PATCH, GAME_PATCH
from aoe2coach.db import log_ingest, replace_rows
from aoe2coach.ingest import aoestats
from aoe2coach.ingest.http import meta_of
from aoe2coach.transform.stats import confianza, wilson

_STAT_TAIL = ("n", "wins", "win_rate", "ci_low", "ci_high", "play_rate", "confianza",
              "source_url", "fetched_at")


def _stat_values(row: dict, patch: int, url: str, fetched: str) -> list:
    p, low, high = wilson(row["wins"], row["n"])
    return [
        row["n"],
        row["wins"],
        p,
        low,
        high,
        row.get("play_rate"),
        confianza(row["n"], patch_vigente=(patch == GAME_PATCH)),
        url,
        fetched,
    ]


def load(con: duckdb.DuckDBPyConnection, patch: int = DATA_PATCH, *, force: bool = False) -> dict:
    payload = aoestats.download(patch, force=force)
    url, fetched = aoestats.source_of(patch)
    resumen: dict[str, int] = {}

    cols = ("patch", "elo_bucket", "map", "civ", "rank", "prior_rank", "avg_game_length",
            *_STAT_TAIL)
    resumen["mart_civ_performance"] = replace_rows(
        con, "mart_civ_performance", cols,
        (
            [r["patch"], r["elo_bucket"], r["map"], r["civ"], r["rank"], r["prior_rank"],
             r["avg_game_length"], *_stat_values(r, patch, url, fetched)]
            for r in aoestats.rows_civ_performance(payload, patch)
        ),
        where="patch = ?", params=[patch],
    )

    cols = ("patch", "elo_bucket", "civ", "opp_civ", *_STAT_TAIL)
    resumen["mart_matchup"] = replace_rows(
        con, "mart_matchup", cols,
        (
            [r["patch"], r["elo_bucket"], r["civ"], r["opp_civ"],
             *_stat_values(r, patch, url, fetched)]
            for r in aoestats.rows_matchup(payload, patch)
        ),
        where="patch = ?", params=[patch],
    )

    cols = ("patch", "elo_bucket", "civ", "duration_bucket", *_STAT_TAIL)
    resumen["mart_civ_by_duration"] = replace_rows(
        con, "mart_civ_by_duration", cols,
        (
            [r["patch"], r["elo_bucket"], r["civ"], r["duration_bucket"],
             *_stat_values(r, patch, url, fetched)]
            for r in aoestats.rows_by_duration(payload, patch)
        ),
        where="patch = ?", params=[patch],
    )

    resumen["mart_map_play_rate"] = replace_rows(
        con, "mart_map_play_rate",
        ("patch", "elo_bucket", "map", "n", "play_rate", "source_url", "fetched_at"),
        (
            [r["patch"], r["elo_bucket"], r["map"], r["n"], r["play_rate"], url, fetched]
            for r in aoestats.rows_map(payload, patch)
        ),
        where="patch = ?", params=[patch],
    )

    archivo = f"aoestats_stats_{patch}.json"
    log_ingest(con, "aoestats:stats", archivo, meta_of(archivo), sum(resumen.values()))
    return resumen


def load_patches(con: duckdb.DuckDBPyConnection, *, force: bool = False) -> int:
    data = aoestats.download_patches(force=force)
    rows = [
        [p["number"], p.get("label"), p.get("release_date"), p.get("url"),
         p.get("description"), p.get("total_games")]
        for p in data
    ]
    return replace_rows(
        con, "mart_patch",
        ("patch", "label", "release_date", "url", "descripcion", "total_games"),
        rows,
    )
