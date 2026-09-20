"""Perfil de cada mapa, derivado de los datos en vez de declarado por opinión.

Dos indicadores, los dos medidos:

- **fc_share**: qué proporción de las aperturas de un mapa son Straight FC. Es el mejor proxy
  de "mapa cerrado": en Arena da 59 % y en Arabia 9 %.
- **naval_share**: proporción de aperturas navales (galleys / fire ships) en el corpus de 2023.
  Sirve para marcar los mapas de agua, que son justo los que el overhaul naval de feb-2026
  dejó sin datos representativos.

Los umbrales de corte son nuestros —eso es juicio, no dato— y están acá arriba para poder
discutirlos. Los mapas sin datos quedan afuera: el motor responde "desconocido" antes que
suponer.
"""

from __future__ import annotations

import duckdb

from aoe2coach.config import DATA_PATCH

#: Aperturas de nivel superior en Pulse (las "* Any" y Straight FC no se solapan entre sí).
_BASE_APERTURAS = (
    "'Scouts Any', 'Range Opener Any', 'MAA Any', "
    "'Premill Drush Any', 'Postmill Drush Any', 'Straight FC'"
)

UMBRAL_CERRADO = 0.40
UMBRAL_SEMICERRADO = 0.18
UMBRAL_AGUA = 0.10
UMBRAL_AGUA_PARCIAL = 0.02

DDL = """
CREATE TABLE IF NOT EXISTS mart_map_profile (
    patch          BIGINT  NOT NULL,
    map            VARCHAR NOT NULL,
    perfil         VARCHAR NOT NULL,   -- abierto | semicerrado | cerrado | desconocido
    fc_share       DOUBLE,
    n_aperturas    BIGINT,
    agua           VARCHAR NOT NULL,   -- si | parcial | no | desconocido
    naval_share    DOUBLE,
    n_naval        BIGINT,
    fuente         VARCHAR NOT NULL
);
"""


def build(con: duckdb.DuckDBPyConnection, patch: int = DATA_PATCH) -> int:
    con.execute(DDL)
    con.execute("DELETE FROM mart_map_profile WHERE patch = ?", [patch])
    con.execute(
        f"""
        INSERT INTO mart_map_profile
        WITH ap AS (
            SELECT map,
                   sum(CASE WHEN opening = 'Straight FC' THEN n ELSE 0 END) AS fc,
                   sum(n) AS tot
            FROM mart_opening
            WHERE patch = ? AND elo_bucket = 'all' AND opening IN ({_BASE_APERTURAS})
            GROUP BY 1
        ),
        nav AS (
            SELECT map,
                   sum(CASE WHEN opening IN ('galleys', 'fires') THEN n ELSE 0 END) AS naval,
                   sum(n) AS tot
            FROM mart_uptime_historico
            GROUP BY 1
            HAVING sum(n) >= 300
        )
        SELECT
            ? AS patch,
            coalesce(ap.map, nav.map) AS map,
            CASE
                WHEN ap.tot IS NULL OR ap.tot < 500 THEN 'desconocido'
                WHEN ap.fc * 1.0 / ap.tot >= {UMBRAL_CERRADO} THEN 'cerrado'
                WHEN ap.fc * 1.0 / ap.tot >= {UMBRAL_SEMICERRADO} THEN 'semicerrado'
                ELSE 'abierto'
            END AS perfil,
            CASE WHEN ap.tot > 0 THEN ap.fc * 1.0 / ap.tot END AS fc_share,
            ap.tot AS n_aperturas,
            CASE
                WHEN nav.tot IS NULL THEN 'desconocido'
                WHEN nav.naval * 1.0 / nav.tot >= {UMBRAL_AGUA} THEN 'si'
                WHEN nav.naval * 1.0 / nav.tot >= {UMBRAL_AGUA_PARCIAL} THEN 'parcial'
                ELSE 'no'
            END AS agua,
            CASE WHEN nav.tot > 0 THEN nav.naval * 1.0 / nav.tot END AS naval_share,
            nav.tot AS n_naval,
            'derivado: fc_share de AoE Pulse (patch actual) + naval_share del corpus 2023'
        FROM ap
        FULL OUTER JOIN nav ON nav.map = ap.map
        WHERE coalesce(ap.map, nav.map) <> 'all'
        """,
        [patch, patch],
    )
    return con.execute(
        "SELECT count(*) FROM mart_map_profile WHERE patch = ?", [patch]
    ).fetchone()[0]
