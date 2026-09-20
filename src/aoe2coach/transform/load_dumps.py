"""Carga y limpieza de los dumps Parquet, y el corpus histórico de uptimes.

Lo que sale de acá NO se mezcla con los agregados del patch actual: son datos de 2023 con otro
balance. Sirven para saber *cómo ejecuta la gente* (a qué minuto sube de edad quien juega tal
apertura, en tal Elo), no para decidir qué civ es buena hoy.
"""

from __future__ import annotations

import duckdb

from aoe2coach.config import ELO_BUCKET_RANGES, SQL_DIR
from aoe2coach.db import log_ingest
from aoe2coach.ingest import dumps
from aoe2coach.ingest.http import meta_of

DDL_UPTIME = """
CREATE TABLE IF NOT EXISTS mart_uptime_historico (
    patch          BIGINT  NOT NULL,
    elo_bucket     VARCHAR NOT NULL,
    map            VARCHAR NOT NULL,
    opening        VARCHAR NOT NULL,
    n              BIGINT  NOT NULL,
    feudal_p50     DOUBLE,
    feudal_p25     DOUBLE,
    feudal_p75     DOUBLE,
    castle_p50     DOUBLE,
    imperial_p50   DOUBLE,
    win_rate       DOUBLE,
    source_url     VARCHAR NOT NULL,
    fetched_at     VARCHAR NOT NULL
);
"""

#: CASE que traduce el Elo del jugador a nuestro tramo, dentro de SQL.
_CASE_ELO = " ".join(
    f"WHEN old_rating >= {lo} AND old_rating < {hi} THEN '{name}'"
    for name, (lo, hi) in ELO_BUCKET_RANGES.items()
)


def _lista_sql(paths) -> str:
    return "[" + ", ".join("'" + str(p).replace("\\", "/") + "'" for p in paths) + "]"


def load(
    con: duckdb.DuckDBPyConnection,
    *,
    ultimas: int = 2,
    con_replay: bool = True,
    force: bool = False,
) -> dict:
    """Baja unas pocas semanas y las deja limpias en la base.

    `ultimas`: semanas más recientes (sin datos de replay, sirven para análisis a nivel partida).
    `con_replay`: agrega las semanas de 2023 que sí traen uptimes y aperturas.
    """
    elegidos = dumps.ultimas(ultimas, force=force)
    if con_replay:
        elegidos += dumps.con_replay(force=force)
    if not elegidos:
        return {"semanas": 0}

    archivos_m, archivos_p = [], []
    for d in elegidos:
        m, p = dumps.descargar(d, force=force)
        archivos_m.append(m)
        archivos_p.append(p)

    sql = (SQL_DIR / "dumps_limpieza.sql").read_text(encoding="utf-8")
    con.execute(sql.replace("{matches}", _lista_sql(archivos_m)).replace(
        "{players}", _lista_sql(archivos_p)))

    total = con.execute("SELECT count(*) FROM raw_matches").fetchone()[0]
    limpias = con.execute("SELECT count(*) FROM clean_matches_1v1").fetchone()[0]
    impares = con.execute(
        "SELECT count(*) FROM raw_matches WHERE num_players % 2 = 1"
    ).fetchone()[0]

    n_uptime = _load_uptimes(con)

    log_ingest(
        con, "aoestats:dumps", ", ".join(d.rango for d in elegidos),
        meta_of(archivos_m[0].name) | {"url": "https://aoestats.io/api/db_dumps"}, total,
    )
    return {
        "semanas": len(elegidos),
        "raw_matches": total,
        "clean_matches_1v1": limpias,
        "descartadas_por_jugadores_impares": impares,
        "mart_uptime_historico": n_uptime,
    }


def _load_uptimes(con: duckdb.DuckDBPyConnection) -> int:
    """Agrega los uptimes por (patch, Elo, mapa, apertura). Sólo filas con datos de replay."""
    con.execute(DDL_UPTIME)
    con.execute("DELETE FROM mart_uptime_historico")
    con.execute(
        f"""
        INSERT INTO mart_uptime_historico
        SELECT
            patch,
            CASE {_CASE_ELO} ELSE 'all' END AS elo_bucket,
            map,
            opening,
            count(*) AS n,
            median(feudal_age_uptime)                              AS feudal_p50,
            quantile_cont(feudal_age_uptime, 0.25)                 AS feudal_p25,
            quantile_cont(feudal_age_uptime, 0.75)                 AS feudal_p75,
            median(castle_age_uptime)                              AS castle_p50,
            median(imperial_age_uptime)                            AS imperial_p50,
            avg(CASE WHEN winner THEN 1.0 ELSE 0.0 END)            AS win_rate,
            'https://aoestats.io/api/db_dumps (dumps semanales)'   AS source_url,
            (SELECT max(fetched_at) FROM ingest_log)               AS fetched_at
        FROM clean_players_1v1
        WHERE feudal_age_uptime IS NOT NULL
          AND opening IS NOT NULL
          AND opening <> 'unknown'
        GROUP BY 1, 2, 3, 4
        HAVING count(*) >= 30
        """
    )
    return con.execute("SELECT count(*) FROM mart_uptime_historico").fetchone()[0]
