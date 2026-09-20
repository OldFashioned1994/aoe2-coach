"""Línea de comandos del pipeline.

    python -m aoe2coach.cli ingest [--force] [--solo aoestats|pulse|techtree|dat|builds|dumps]

`dumps` no entra en la ingesta completa: baja varios MB por semana y sólo hace falta para el
corpus histórico de uptimes. Se pide explícitamente.
    python -m aoe2coach.cli check
    python -m aoe2coach.cli info
"""

from __future__ import annotations

import argparse
import sys

from aoe2coach.config import (
    DATA_CUTOFF,
    DATA_PATCH,
    DATA_PATCH_DATE,
    DB_PATH,
    GAME_PATCH,
    GAME_PATCH_DATE,
    ensure_dirs,
)
from aoe2coach.db import connect
from aoe2coach.transform import load_aoepulse, load_aoestats, load_dumps, load_ref


def _p(msg: str = "") -> None:
    print(msg, flush=True)


def _consola_utf8() -> None:
    """La consola de Windows abre en cp1252 y revienta con flechas y acentos."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def cmd_ingest(args: argparse.Namespace) -> int:
    ensure_dirs()
    con = connect()
    solo = args.solo
    force = args.force

    if solo in (None, "aoestats"):
        _p("→ aoestats: patches y agregados…")
        _p(f"  mart_patch: {load_aoestats.load_patches(con, force=force)} filas")
        for tabla, n in load_aoestats.load(con, DATA_PATCH, force=force).items():
            _p(f"  {tabla}: {n} filas")

    if solo in (None, "techtree"):
        _p("→ aoe2techtree: unidades, techs, edificios y civs…")
        for tabla, n in load_ref.load_techtree(con, force=force).items():
            _p(f"  {tabla}: {n} filas")

    if solo in (None, "dat"):
        _p("→ aoe2dat: tasas de recolección…")
        _p(f"  ref_gather_rate: {load_ref.load_gather_rates(con, force=force)} filas")

    if solo in (None, "builds"):
        _p("→ rtsbuilds: build orders…")
        for tabla, n in load_ref.load_builds(con, force=force).items():
            _p(f"  {tabla}: {n} filas")

    if solo == "dumps":
        _p("→ aoestats: dumps Parquet (nivel partida + corpus histórico de uptimes)…")
        for k, v in load_dumps.load(con, force=force).items():
            _p(f"  {k}: {v}")

    if solo in (None, "pulse"):
        _p("→ AoE Pulse: aperturas (tarda: es una request por mapa y tramo de Elo)…")
        res = load_aoepulse.load(con, DATA_PATCH, force=force)
        _p(f"  mart_opening: {res['mart_opening']} filas")
        _p(f"  mart_opening_matchup: {res['mart_opening_matchup']} filas")
        _p(f"  mapas cubiertos: {', '.join(res['mapas_cubiertos'])}")
        if res["mapas_omitidos_por_play_rate"]:
            _p(f"  omitidos por play rate < 1%: {', '.join(res['mapas_omitidos_por_play_rate'])}")
        if res["mapas_sin_equivalente_en_pulse"]:
            _p(f"  sin equivalente en Pulse: {', '.join(res['mapas_sin_equivalente_en_pulse'])}")

    con.close()
    _p(f"\nBase: {DB_PATH}")
    return 0


def cmd_recomendar(args: argparse.Namespace) -> int:
    from aoe2coach.engine.modelos import Contexto
    from aoe2coach.engine.motor import recomendar
    from aoe2coach.engine.presentacion import render_texto

    con = connect(read_only=True)
    ctx = Contexto(
        civ=(args.civ or "").lower() or None,
        mapa=args.mapa.lower(),
        elo=args.elo,
        civ_rival=(args.rival or "").lower() or None,
    )
    _p(render_texto(recomendar(con, ctx)))
    con.close()
    return 0


def cmd_civ(args: argparse.Namespace) -> int:
    """Ficha de una civilización: lo mismo que muestra la web, en consola."""
    from aoe2coach.config import elo_bucket
    from aoe2coach.engine.civ import ficha

    con = connect(read_only=True)
    bucket = elo_bucket(args.elo) if args.elo else "all"
    f = ficha(con, args.civ.lower(), bucket)
    con.close()
    if not f:
        _p(f"No existe la civilización {args.civ!r}")
        return 1

    _p("")
    _p(f"{f['nombre'].upper()} — {f['secciones']['tipo']}  (tramo {bucket})")
    _p("")
    for b in f["secciones"]["bonos"]:
        _p(f"  · {b}")

    for etiqueta, clave in (
        ("Unidad única", "unidad_unica"),
        ("Tecnologías únicas", "techs_unicas"),
        ("Bonificación de equipo", "equipo"),
    ):
        if f["secciones"][clave]:
            _p("")
            _p(f"  {etiqueta}:")
            for x in f["secciones"][clave]:
                _p(f"    · {x}")

    _p("")
    _p(f"  Win rate general: {f['general'].texto()}")
    if f["perfil_temporal"]["veredicto"]:
        _p(f"  {f['perfil_temporal']['veredicto']}")

    if f["mejores_mapas"]:
        _p("")
        _p("  Mejores mapas:")
        for m in f["mejores_mapas"]:
            _p(f"    {m['mapa']:<16} {m['win_rate'] * 100:5.1f}%   n={m['n']}")

    if f["peores_matchups"]:
        _p("")
        _p("  Sufre contra:")
        for m in f["peores_matchups"]:
            _p(f"    {m['civ']:<16} {m['win_rate'] * 100:5.1f}%   n={m['n']}")

    _p("")
    _p("  Qué le falta:")
    if not f["carencias"]:
        _p("    nada importante: árbol tecnológico completo para 1v1")
    for c in f["carencias"]:
        _p(f"    · {c['que']} ({c['tipo']}) — {c['por_que']}")
    _p("")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    """Levanta la web local. La app vive en localhost y no expone nada afuera."""
    import uvicorn

    _p(f"AoE2 Coach en http://127.0.0.1:{args.puerto}  (Ctrl+C para cortar)")
    uvicorn.run("aoe2coach.api.app:app", host="127.0.0.1", port=args.puerto,
                reload=args.reload, log_level="warning")
    return 0


def cmd_info(_: argparse.Namespace) -> int:
    con = connect(read_only=True)
    _p(f"Datos: patch {DATA_PATCH} ({DATA_PATCH_DATE}), partidas hasta {DATA_CUTOFF}")
    _p(f"Juego: patch {GAME_PATCH} ({GAME_PATCH_DATE}) — los datos NO cubren el patch vigente")
    _p("")
    for (tabla,) in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall():
        n = con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
        _p(f"  {tabla:<26} {n:>8}")
    _p("")
    _p("Última ingesta por fuente:")
    for f, fecha, filas in con.execute(
        "SELECT fuente, max(fetched_at), sum(filas) FROM ingest_log GROUP BY fuente ORDER BY 1"
    ).fetchall():
        _p(f"  {f:<20} {fecha or '-':<22} {filas} filas")
    con.close()
    return 0


def cmd_check(_: argparse.Namespace) -> int:
    from aoe2coach.transform.checks import run_checks

    con = connect(read_only=True)
    fallas = run_checks(con)
    con.close()
    for nivel, nombre, detalle in fallas:
        _p(f"  [{nivel}] {nombre}: {detalle}")
    errores = [f for f in fallas if f[0] == "ERROR"]
    _p(f"\n{len(fallas)} observaciones, {len(errores)} errores.")
    return 1 if errores else 0


def main(argv: list[str] | None = None) -> int:
    _consola_utf8()
    parser = argparse.ArgumentParser(prog="aoe2coach")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="descarga y carga las fuentes")
    p.add_argument("--force", action="store_true", help="ignora la caché en disco")
    p.add_argument("--solo", choices=["aoestats", "pulse", "techtree", "dat", "builds", "dumps"])
    p.set_defaults(func=cmd_ingest)

    r = sub.add_parser("recomendar", help="estrategia y build order para un contexto")
    r.add_argument("--civ", help="tu civilización (en inglés, como la nombra la fuente)")
    r.add_argument("--mapa", required=True)
    r.add_argument("--elo", type=int, required=True)
    r.add_argument("--rival", help="civilización del rival, si la conocés")
    r.set_defaults(func=cmd_recomendar)

    c = sub.add_parser("civ", help="ficha de una civilización: bonos, fortalezas y carencias")
    c.add_argument("civ")
    c.add_argument("--elo", type=int, help="para ver los datos de tu tramo")
    c.set_defaults(func=cmd_civ)

    w = sub.add_parser("web", help="levanta la web local")
    w.add_argument("--puerto", type=int, default=8000)
    w.add_argument("--reload", action="store_true", help="recarga al editar código")
    w.set_defaults(func=cmd_web)

    sub.add_parser("info", help="estado de la base").set_defaults(func=cmd_info)
    sub.add_parser("check", help="controles de calidad de datos").set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
