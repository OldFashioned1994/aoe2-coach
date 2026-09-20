"""Web local: formulario de contexto, reporte, checklist y explorador de datos.

Se levanta con `python -m aoe2coach.cli web` y vive en localhost. No hay build step ni
dependencias de JavaScript: HTML que rinde el servidor y un poco de JS propio para la
checklist, que es lo único interactivo de verdad.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from aoe2coach.config import (
    DATA_CUTOFF,
    DATA_PATCH,
    DATA_PATCH_DATE,
    DB_PATH,
    GAME_PATCH,
    GAME_PATCH_DATE,
    elo_bucket,
)
from aoe2coach.db import connect
from aoe2coach.engine.modelos import Contexto
from aoe2coach.engine.motor import recomendar

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="AoE2 Coach", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
plantillas = Jinja2Templates(directory=str(WEB / "templates"))


def db() -> duckdb.DuckDBPyConnection:
    """Una conexión por request: DuckDB en modo lectura admite varias sin bloquear."""
    return connect(DB_PATH, read_only=True)


def _catalogos(con: duckdb.DuckDBPyConnection) -> dict:
    mapas = [
        r[0] for r in con.execute(
            "SELECT map FROM mart_map_play_rate WHERE patch = ? AND elo_bucket = 'all' "
            "ORDER BY play_rate DESC", [DATA_PATCH]
        ).fetchall()
    ]
    civs = [
        r[0] for r in con.execute(
            "SELECT DISTINCT civ FROM mart_civ_performance WHERE patch = ? ORDER BY 1",
            [DATA_PATCH]
        ).fetchall()
    ]
    return {"mapas": mapas, "civs": civs}


def _contexto_base(request: Request) -> dict:
    return {
        "request": request,
        "data_patch": DATA_PATCH,
        "data_patch_date": DATA_PATCH_DATE,
        "data_cutoff": DATA_CUTOFF,
        "game_patch": GAME_PATCH,
        "game_patch_date": GAME_PATCH_DATE,
    }


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    con = db()
    try:
        datos = _contexto_base(request) | _catalogos(con)
        return plantillas.TemplateResponse(request, "index.html", datos)
    finally:
        con.close()


@app.get("/reporte", response_class=HTMLResponse)
def reporte(
    request: Request,
    mapa: str = Query(...),
    elo: int = Query(...),
    civ: str | None = None,
    rival: str | None = None,
):
    con = db()
    try:
        ctx = Contexto(
            civ=(civ or "").lower() or None,
            mapa=mapa.lower(),
            elo=elo,
            civ_rival=(rival or "").lower() or None,
        )
        r = recomendar(con, ctx)
        datos = _contexto_base(request) | {"r": r, "bucket": elo_bucket(elo)}
        return plantillas.TemplateResponse(request, "reporte.html", datos)
    finally:
        con.close()


@app.get("/checklist/{build_id}", response_class=HTMLResponse)
def checklist(request: Request, build_id: str, civ: str | None = None):
    """Vista para seguir el build mientras jugás: un paso grande por vez."""
    con = db()
    try:
        cabecera = con.execute(
            "SELECT nombre, civ, autor, fuente FROM ref_build_order WHERE build_id = ?",
            [build_id],
        ).fetchone()
        if not cabecera:
            return HTMLResponse("<h1>No existe ese build</h1>", status_code=404)
        pasos = con.execute(
            "SELECT paso, villager_count, age, food, wood, gold, stone, time, notas "
            "FROM ref_build_step WHERE build_id = ? ORDER BY paso", [build_id]
        ).fetchall()
        datos = _contexto_base(request) | {
            "build_id": build_id,
            "nombre": cabecera[0],
            "civ_build": cabecera[1],
            "autor": cabecera[2],
            "fuente": cabecera[3],
            "pasos": pasos,
            "civ": civ,
        }
        return plantillas.TemplateResponse(request, "checklist.html", datos)
    finally:
        con.close()


@app.get("/datos", response_class=HTMLResponse)
def explorador(
    request: Request,
    mapa: str = "all",
    bucket: str = "all",
    orden: str = "win_rate",
):
    """Win rates por civ, mapa y tramo de Elo, para estudiar por tu cuenta."""
    con = db()
    try:
        columna = "win_rate" if orden not in ("n", "play_rate", "civ") else orden
        filas = con.execute(
            f"SELECT civ, n, win_rate, ci_low, ci_high, play_rate FROM mart_civ_performance "
            f"WHERE patch = ? AND map = ? AND elo_bucket = ? ORDER BY {columna} DESC",
            [DATA_PATCH, mapa, bucket],
        ).fetchall()
        aperturas = con.execute(
            "SELECT opening, n, win_rate, ci_low, ci_high FROM mart_opening "
            "WHERE patch = ? AND map = ? AND elo_bucket = ? ORDER BY n DESC",
            [DATA_PATCH, mapa if mapa != "all" else "all", bucket],
        ).fetchall()
        datos = _contexto_base(request) | _catalogos(con) | {
            "filas": filas, "aperturas": aperturas, "mapa": mapa, "bucket": bucket,
            "orden": columna,
        }
        return plantillas.TemplateResponse(request, "datos.html", datos)
    finally:
        con.close()
