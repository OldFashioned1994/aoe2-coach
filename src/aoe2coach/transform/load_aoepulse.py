"""Carga de aperturas (AoE Pulse) a `mart_opening` y `mart_opening_matchup`.

Cobertura: por defecto los mapas con al menos 1 % de play rate en aoestats, más el agregado
`all`, por los 6 tramos de Elo. Lo que queda afuera se informa por pantalla — un recorte
silencioso se leería como "cubrimos todo" cuando no es cierto.
"""

from __future__ import annotations

import duckdb

from aoe2coach.config import DATA_PATCH, ELO_BUCKETS, GAME_PATCH
from aoe2coach.db import log_ingest, replace_rows
from aoe2coach.ingest import aoepulse
from aoe2coach.ingest.http import meta_of
from aoe2coach.transform.stats import confianza, wilson

_STAT_TAIL = ("n", "wins", "win_rate", "ci_low", "ci_high", "play_rate", "confianza",
              "source_url", "fetched_at")

UMBRAL_PLAY_RATE = 0.01


def mapas_objetivo(con: duckdb.DuckDBPyConnection, patch: int = DATA_PATCH) -> tuple[list[str], list[str]]:
    """Devuelve (incluidos, omitidos) según play rate en aoestats."""
    filas = con.execute(
        "SELECT map, play_rate FROM mart_map_play_rate "
        "WHERE patch = ? AND elo_bucket = 'all' ORDER BY play_rate DESC",
        [patch],
    ).fetchall()
    incluidos = [m for m, pr in filas if (pr or 0) >= UMBRAL_PLAY_RATE]
    omitidos = [m for m, pr in filas if (pr or 0) < UMBRAL_PLAY_RATE]
    return incluidos, omitidos


def _stat_values(row: dict, patch: int, url: str, fetched: str) -> list:
    p, low, high = wilson(row["wins"], row["n"])
    return [row["n"], row["wins"], p, low, high, None,
            confianza(row["n"], patch_vigente=(patch == GAME_PATCH)), url, fetched]


def load(
    con: duckdb.DuckDBPyConnection,
    patch: int = DATA_PATCH,
    *,
    mapas: list[str] | None = None,
    force: bool = False,
) -> dict:
    info = aoepulse.download_info(force=force)
    if mapas is None:
        mapas, omitidos = mapas_objetivo(con, patch)
    else:
        omitidos = []
    objetivo = ["all", *mapas]

    filas_ap: list[list] = []
    filas_mu: list[list] = []
    sin_datos: list[str] = []
    archivo = "aoepulse_info.json"  # por si no queda ningún mapa que recorrer

    for mapa in objetivo:
        if mapa != "all" and not aoepulse.map_ids(info, mapa):
            sin_datos.append(mapa)
            continue
        for elo in ELO_BUCKETS:
            data, archivo = aoepulse.download_openings(info, mapa, elo, patch, force=force)
            url, fetched = aoepulse.source_of(archivo)
            for r in aoepulse.rows_openings(data, mapa, elo, patch):
                filas_ap.append([r["patch"], r["elo_bucket"], r["map"], r["opening"],
                                 *_stat_values(r, patch, url, fetched)])

            data, archivo = aoepulse.download_opening_matchups(info, mapa, elo, patch, force=force)
            url, fetched = aoepulse.source_of(archivo)
            for r in aoepulse.rows_opening_matchups(data, mapa, elo, patch):
                filas_mu.append([r["patch"], r["elo_bucket"], r["map"], r["opening"],
                                 r["opp_opening"], *_stat_values(r, patch, url, fetched)])

    n_ap = replace_rows(
        con, "mart_opening", ("patch", "elo_bucket", "map", "opening", *_STAT_TAIL),
        filas_ap, where="patch = ?", params=[patch],
    )
    n_mu = replace_rows(
        con, "mart_opening_matchup",
        ("patch", "elo_bucket", "map", "opening", "opp_opening", *_STAT_TAIL),
        filas_mu, where="patch = ?", params=[patch],
    )
    log_ingest(con, "aoepulse", "aoepulse_*.json", meta_of(archivo), n_ap + n_mu)
    return {
        "mart_opening": n_ap,
        "mart_opening_matchup": n_mu,
        "mapas_cubiertos": objetivo,
        "mapas_omitidos_por_play_rate": omitidos,
        "mapas_sin_equivalente_en_pulse": sin_datos,
    }
