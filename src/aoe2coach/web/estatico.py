"""Genera el sitio estático que se publica en GitHub Pages.

Por qué existe: la app es un servidor Python con una base de 242 MB, y Pages sólo sirve
archivos. En vez de reescribir el motor en JavaScript —que sería tener dos motores y que
divergieran—, acá se **pregenera** con el mismo motor, las mismas plantillas y los mismos
datos. Lo que se publica es el resultado, no una segunda implementación.

Qué se pregenera y qué no:

- Fichas de civ y explorador de datos: todos los cortes.
- Reporte: los mapas con datos de aperturas y todas las civs, sin civ rival. El matchup contra
  un rival concreto queda sólo en la app local: son 48 × 48 combinaciones por mapa y tramo, y
  no entra en un sitio estático razonable.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
from jinja2 import Environment, FileSystemLoader, select_autoescape

from aoe2coach.config import DATA_PATCH, DATA_PATCH_DATE, DATA_CUTOFF, GAME_PATCH, GAME_PATCH_DATE
from aoe2coach.engine import civ as civ_mod
from aoe2coach.engine.modelos import Contexto
from aoe2coach.engine.motor import recomendar
from aoe2coach.web.enlaces import url_estatica

WEB = Path(__file__).resolve().parent
BUCKETS = ("all", "low", "med_low", "medium", "med_high", "high")

#: Elo de referencia de cada tramo, para que el reporte sepa qué contexto armar.
ELO_POR_BUCKET = {
    "all": 1000, "low": 500, "med_low": 1100, "medium": 1300, "med_high": 1600, "high": 1900,
}


def _entorno() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(WEB / "templates")),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["u"] = url_estatica
    return env


def _base(con: duckdb.DuckDBPyConnection) -> dict:
    return {
        "request": None,
        "data_patch": DATA_PATCH,
        "data_patch_date": DATA_PATCH_DATE,
        "data_cutoff": DATA_CUTOFF,
        "game_patch": GAME_PATCH,
        "game_patch_date": GAME_PATCH_DATE,
    }


def _escribir(destino: Path, nombre: str, html: str) -> None:
    (destino / nombre).write_text(html, encoding="utf-8")


def generar(
    con: duckdb.DuckDBPyConnection,
    destino: Path,
    mapas_reporte: tuple[str, ...] = ("arabia", "arena", "megarandom"),
) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    env = _entorno()
    base = _base(con)
    cuenta = {"civs": 0, "datos": 0, "reportes": 0, "checklists": 0}

    shutil.copy(WEB / "static" / "estilo.css", destino / "estilo.css")
    shutil.copy(WEB / "static" / "checklist.js", destino / "checklist.js")

    civs = [
        r[0] for r in con.execute("SELECT civ FROM ref_civ ORDER BY civ").fetchall()
    ]
    mapas = [
        r[0] for r in con.execute(
            "SELECT map FROM mart_map_play_rate WHERE patch = ? AND elo_bucket = 'all' "
            "ORDER BY play_rate DESC", [DATA_PATCH]
        ).fetchall()
    ]
    con_datos = [
        r[0] for r in con.execute(
            "SELECT DISTINCT civ FROM mart_civ_performance WHERE patch = ?", [DATA_PATCH]
        ).fetchall()
    ]

    # 1. Fichas de civilización
    plantilla = env.get_template("ficha.html")
    for c in civs:
        for b in BUCKETS:
            f = civ_mod.ficha(con, c, b)
            if not f:
                continue
            _escribir(destino, url_estatica("civ", civ=c, bucket=b),
                      plantilla.render(**base, f=f, etiquetas=civ_mod.DURACION_ETIQUETAS))
            cuenta["civs"] += 1

    # 2. Explorador de datos
    plantilla = env.get_template("datos.html")
    for m in ["all", *mapas]:
        for b in BUCKETS:
            filas = con.execute(
                "SELECT civ, n, win_rate, ci_low, ci_high, play_rate FROM mart_civ_performance "
                "WHERE patch = ? AND map = ? AND elo_bucket = ? ORDER BY win_rate DESC",
                [DATA_PATCH, m, b],
            ).fetchall()
            aperturas = con.execute(
                "SELECT opening, n, win_rate, ci_low, ci_high FROM mart_opening "
                "WHERE patch = ? AND map = ? AND elo_bucket = ? ORDER BY n DESC",
                [DATA_PATCH, m, b],
            ).fetchall()
            _escribir(destino, url_estatica("datos", mapa=m, bucket=b),
                      plantilla.render(**base, filas=filas, aperturas=aperturas, mapa=m,
                                       bucket=b, orden="win_rate", mapas=mapas, civs=con_datos))
            cuenta["datos"] += 1

    # 3. Reportes: por mapa, tramo y civ (incluida la opción "que me la recomiende")
    plantilla = env.get_template("reporte.html")
    for m in mapas_reporte:
        for b in BUCKETS:
            elo = ELO_POR_BUCKET[b]
            for c in [None, *con_datos]:
                r = recomendar(con, Contexto(civ=c, mapa=m, elo=elo))
                _escribir(
                    destino,
                    url_estatica("reporte", mapa=m, bucket=b, civ=c),
                    plantilla.render(**base, r=r, bucket=b),
                )
                cuenta["reportes"] += 1

    # 4. Checklists de todos los builds
    plantilla = env.get_template("checklist.html")
    for build_id, nombre, civ_b, autor, fuente in con.execute(
        "SELECT build_id, nombre, civ, autor, fuente FROM ref_build_order"
    ).fetchall():
        pasos = con.execute(
            "SELECT paso, villager_count, age, food, wood, gold, stone, time, notas "
            "FROM ref_build_step WHERE build_id = ? ORDER BY paso", [build_id]
        ).fetchall()
        _escribir(destino, url_estatica("checklist", build_id=build_id),
                  plantilla.render(**base, build_id=build_id, nombre=nombre, civ_build=civ_b,
                                   autor=autor, fuente=fuente, pasos=pasos, civ=None))
        cuenta["checklists"] += 1

    # 5. Portada: el formulario arma el nombre del archivo y redirige
    _escribir(destino, "index.html", env.get_template("index_estatico.html").render(
        **base, civs=con_datos, mapas=mapas_reporte, buckets=BUCKETS,
        elo_por_bucket=ELO_POR_BUCKET, todos_los_mapas=mapas,
    ))

    # Pages no publica carpetas que empiecen con guion bajo si no está este archivo.
    (destino / ".nojekyll").write_text("", encoding="utf-8")
    return cuenta
