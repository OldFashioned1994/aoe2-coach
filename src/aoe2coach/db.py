"""Acceso a DuckDB y esquema de la base.

Convención de nombres (docs/design.md §5):
  ref_*   datos del juego y catálogos
  mart_*  tablas que consulta el motor, con la estadística ya resuelta

La capa `raw_` vive como archivos en `data/raw/` con su sidecar `.meta.json`, más la tabla
`ingest_log`: duplicar los JSON crudos dentro de la base no aportaba nada y los hacía menos
inspeccionables.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from aoe2coach.config import DB_PATH

#: Columnas comunes a toda tabla estadística. Ninguna fila entra sin n, intervalo y fuente.
_STAT_COLS = """
    n            BIGINT  NOT NULL,
    wins         BIGINT  NOT NULL,
    win_rate     DOUBLE  NOT NULL,
    ci_low       DOUBLE  NOT NULL,
    ci_high      DOUBLE  NOT NULL,
    play_rate    DOUBLE,
    confianza    VARCHAR NOT NULL,
    source_url   VARCHAR NOT NULL,
    fetched_at   VARCHAR NOT NULL
"""

DDL = f"""
CREATE TABLE IF NOT EXISTS ingest_log (
    fuente       VARCHAR NOT NULL,
    archivo      VARCHAR NOT NULL,
    url          VARCHAR,
    fetched_at   VARCHAR,
    bytes        BIGINT,
    md5          VARCHAR,
    filas        BIGINT,
    loaded_at    VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS mart_civ_performance (
    patch            BIGINT  NOT NULL,
    elo_bucket       VARCHAR NOT NULL,
    map              VARCHAR NOT NULL,
    civ              VARCHAR NOT NULL,
    rank             BIGINT,
    prior_rank       BIGINT,
    avg_game_length  DOUBLE,
    {_STAT_COLS}
);

CREATE TABLE IF NOT EXISTS mart_matchup (
    patch        BIGINT  NOT NULL,
    elo_bucket   VARCHAR NOT NULL,
    civ          VARCHAR NOT NULL,
    opp_civ      VARCHAR NOT NULL,
    {_STAT_COLS}
);

CREATE TABLE IF NOT EXISTS mart_civ_by_duration (
    patch            BIGINT  NOT NULL,
    elo_bucket       VARCHAR NOT NULL,
    civ              VARCHAR NOT NULL,
    duration_bucket  VARCHAR NOT NULL,
    {_STAT_COLS}
);

CREATE TABLE IF NOT EXISTS mart_opening (
    patch        BIGINT  NOT NULL,
    elo_bucket   VARCHAR NOT NULL,
    map          VARCHAR NOT NULL,
    opening      VARCHAR NOT NULL,
    {_STAT_COLS}
);

CREATE TABLE IF NOT EXISTS mart_opening_matchup (
    patch        BIGINT  NOT NULL,
    elo_bucket   VARCHAR NOT NULL,
    map          VARCHAR NOT NULL,
    opening      VARCHAR NOT NULL,
    opp_opening  VARCHAR NOT NULL,
    {_STAT_COLS}
);

CREATE TABLE IF NOT EXISTS mart_map_play_rate (
    patch        BIGINT  NOT NULL,
    elo_bucket   VARCHAR NOT NULL,
    map          VARCHAR NOT NULL,
    n            BIGINT  NOT NULL,
    play_rate    DOUBLE,
    source_url   VARCHAR NOT NULL,
    fetched_at   VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS mart_patch (
    patch        BIGINT PRIMARY KEY,
    label        VARCHAR,
    release_date VARCHAR,
    url          VARCHAR,
    descripcion  VARCHAR,
    total_games  BIGINT
);

-- --- ref_: datos exactos del juego y catálogos -------------------------------

CREATE TABLE IF NOT EXISTS ref_unit (
    id BIGINT PRIMARY KEY, internal_name VARCHAR, nombre VARCHAR,
    food BIGINT, wood BIGINT, gold BIGINT, stone BIGINT,
    hp BIGINT, attack BIGINT, melee_armor BIGINT, pierce_armor BIGINT,
    range DOUBLE, reload_time DOUBLE, attack_delay DOUBLE, accuracy BIGINT,
    speed DOUBLE, line_of_sight DOUBLE, train_time BIGINT,
    attacks_json VARCHAR, armours_json VARCHAR
);

CREATE TABLE IF NOT EXISTS ref_tech (
    id BIGINT PRIMARY KEY, internal_name VARCHAR, nombre VARCHAR,
    food BIGINT, wood BIGINT, gold BIGINT, stone BIGINT,
    research_time DOUBLE, repeatable BOOLEAN
);

CREATE TABLE IF NOT EXISTS ref_building (
    id BIGINT PRIMARY KEY, internal_name VARCHAR, nombre VARCHAR,
    food BIGINT, wood BIGINT, gold BIGINT, stone BIGINT,
    hp BIGINT, build_time DOUBLE
);

CREATE TABLE IF NOT EXISTS ref_civ (
    civ VARCHAR PRIMARY KEY, nombre_en VARCHAR, nombre_es VARCHAR, era VARCHAR,
    bonos_texto VARCHAR, bonos_texto_en VARCHAR,
    n_units BIGINT, n_techs BIGINT, n_buildings BIGINT
);

CREATE TABLE IF NOT EXISTS ref_civ_tech_tree (
    civ VARCHAR NOT NULL, tipo VARCHAR NOT NULL, id BIGINT NOT NULL,
    nombre_nodo VARCHAR, disponible BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_gather_rate (
    tarea VARCHAR PRIMARY KEY, unidad_interna VARCHAR, recurso VARCHAR,
    work_rate DOUBLE, speed DOUBLE, capacidad DOUBLE, fuente VARCHAR
);

CREATE TABLE IF NOT EXISTS ref_tech_effect (
    tech VARCHAR NOT NULL, tarea VARCHAR NOT NULL, unidad_interna VARCHAR,
    multiplicador DOUBLE NOT NULL, fuente VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_build_order (
    build_id VARCHAR PRIMARY KEY, nombre VARCHAR, civ VARCHAR,
    autor VARCHAR, fuente VARCHAR, repo VARCHAR,
    n_pasos BIGINT, villagers_final BIGINT, duracion_s BIGINT
);

CREATE TABLE IF NOT EXISTS ref_build_step (
    build_id VARCHAR NOT NULL, paso BIGINT NOT NULL,
    villager_count BIGINT, age BIGINT,
    food BIGINT, wood BIGINT, gold BIGINT, stone BIGINT, builder BIGINT,
    time VARCHAR, time_s BIGINT, notas VARCHAR
);
"""


def connect(path: Path | str = DB_PATH, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    if not read_only:
        con.execute(DDL)
    return con


def replace_rows(
    con: duckdb.DuckDBPyConnection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    where: str | None = None,
    params: Sequence[Any] = (),
) -> int:
    """Reemplaza un subconjunto de la tabla (idempotente: re-ingerir no duplica)."""
    rows = list(rows)
    if where:
        con.execute(f"DELETE FROM {table} WHERE {where}", list(params))
    else:
        con.execute(f"DELETE FROM {table}")
    if rows:
        placeholders = ", ".join("?" * len(columns))
        con.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", rows
        )
    return len(rows)


def log_ingest(
    con: duckdb.DuckDBPyConnection, fuente: str, archivo: str, meta: dict, filas: int
) -> None:
    con.execute("DELETE FROM ingest_log WHERE fuente = ? AND archivo = ?", [fuente, archivo])
    con.execute(
        "INSERT INTO ingest_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            fuente,
            archivo,
            meta.get("url"),
            meta.get("fetched_at"),
            meta.get("bytes"),
            meta.get("md5"),
            filas,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ],
    )
