"""Carga de los datos exactos del juego y de los build orders a las tablas `ref_*`."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import duckdb

from aoe2coach.db import log_ingest, replace_rows
from aoe2coach.ingest import builds as builds_mod
from aoe2coach.ingest import datfile, techtree
from aoe2coach.ingest.http import meta_of


def _cargar(con, tabla: str, filas: Iterable[dict], columnas: Sequence[str]) -> int:
    filas = list(filas)
    return replace_rows(con, tabla, columnas, ([f[c] for c in columnas] for f in filas))


def load_techtree(con: duckdb.DuckDBPyConnection, *, force: bool = False) -> dict:
    data = techtree.download(force=force)
    strings = techtree.download_strings("es", force=force)
    strings_en = techtree.download_strings("en", force=force)
    resumen = {
        "ref_unit": _cargar(
            con, "ref_unit", techtree.rows_units(data, strings),
            ("id", "internal_name", "nombre", "food", "wood", "gold", "stone", "hp", "attack",
             "melee_armor", "pierce_armor", "range", "reload_time", "attack_delay", "accuracy",
             "speed", "line_of_sight", "train_time", "attacks_json", "armours_json"),
        ),
        "ref_tech": _cargar(
            con, "ref_tech", techtree.rows_techs(data, strings, strings_en),
            ("id", "internal_name", "nombre", "food", "wood", "gold", "stone",
             "research_time", "repeatable"),
        ),
        "ref_building": _cargar(
            con, "ref_building", techtree.rows_buildings(data, strings),
            ("id", "internal_name", "nombre", "food", "wood", "gold", "stone", "hp",
             "build_time"),
        ),
        "ref_civ_tech_tree": _cargar(
            con, "ref_civ_tech_tree",
            (
                fila
                for civ_en in data["civs"]
                for fila in techtree.rows_civ_tech_tree(
                    civ_en, techtree.download_tree(civ_en, force=force)
                )
            ),
            ("civ", "tipo", "id", "nombre_nodo", "disponible"),
        ),
        "ref_civ": _cargar(
            con, "ref_civ", techtree.rows_civs(data, strings, strings_en),
            ("civ", "nombre_en", "nombre_es", "era", "bonos_texto", "bonos_texto_en",
             "n_units", "n_techs", "n_buildings"),
        ),
    }
    log_ingest(con, "aoe2techtree", techtree.ARCHIVO_DATA, meta_of(techtree.ARCHIVO_DATA),
               sum(resumen.values()))
    return resumen


def load_gather_rates(con: duckdb.DuckDBPyConnection, *, force: bool = False) -> int:
    destilado = datfile.destilar(force=force) if force else datfile.cargar()
    fuente = destilado["_fuente"]["url"]
    filas = [
        [tarea, v["unidad_interna"], v["recurso"], v["work_rate"], v["speed"], v["capacidad"],
         fuente]
        for tarea, v in destilado["tasas"].items()
    ]
    n = replace_rows(
        con, "ref_gather_rate",
        ("tarea", "unidad_interna", "recurso", "work_rate", "speed", "capacidad", "fuente"),
        filas,
    )
    efectos = datfile.destilar_efectos_eco(force=force) if force else datfile.cargar_efectos_eco()
    n_ef = replace_rows(
        con, "ref_tech_effect",
        ("tech", "tarea", "unidad_interna", "multiplicador", "fuente"),
        [[e["tech"], e["tarea"], e["unidad_interna"], e["multiplicador"],
          efectos["_fuente"]["url"]] for e in efectos["efectos"]],
    )
    log_ingest(con, "aoe2dat", datfile.ARCHIVO, meta_of(datfile.ARCHIVO), n + n_ef)
    return n + n_ef


def load_builds(con: duckdb.DuckDBPyConnection, *, force: bool = False) -> dict:
    builds_mod.descargar_todos(force=force)
    data = builds_mod.leer_locales()
    resumen = {
        "ref_build_order": _cargar(
            con, "ref_build_order", builds_mod.rows_build_orders(data),
            ("build_id", "nombre", "civ", "autor", "fuente", "repo", "n_pasos",
             "villagers_final", "duracion_s"),
        ),
        "ref_build_step": _cargar(
            con, "ref_build_step", builds_mod.rows_build_steps(data),
            ("build_id", "paso", "villager_count", "age", "food", "wood", "gold", "stone",
             "builder", "time", "time_s", "notas"),
        ),
    }
    log_ingest(con, "rtsbuilds", "data/builds/*.json", meta_of("rtsbuilds_tree.json"),
               resumen["ref_build_order"])
    return resumen
