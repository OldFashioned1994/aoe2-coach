"""Tests contra la base ya cargada.

Se saltean si todavía no se corrió `python -m aoe2coach.cli ingest`, para que el repo se pueda
clonar y testear sin red.
"""

from __future__ import annotations

import pytest

from aoe2coach.config import DB_PATH
from aoe2coach.db import connect
from aoe2coach.transform.checks import check_wilson_vs_fuente, run_checks

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="falta correr la ingesta")


@pytest.fixture(scope="module")
def con():
    c = connect(read_only=True)
    yield c
    c.close()


def test_criterio_de_aceptacion_fase1(con):
    """Francos en Arabia tiene que reproducir el número publicado por aoestats.

    Verificado contra la API el 17-ago-2026: 51,40 % con n = 51.920.
    """
    fila = con.execute(
        "SELECT n, win_rate, ci_low, ci_high FROM mart_civ_performance "
        "WHERE patch = 162286 AND elo_bucket = 'all' AND map = 'arabia' AND civ = 'franks'"
    ).fetchone()
    assert fila is not None, "no está la fila de Francos en Arabia"
    n, wr, low, high = fila
    assert n == 51920
    assert abs(wr * 100 - 51.40) < 0.1
    assert low < wr < high


def test_nuestro_wilson_coincide_con_la_fuente(con):
    """Si el intervalo propio se aleja del de aoestats, algo se rompió."""
    peor = check_wilson_vs_fuente(con)
    assert peor < 0.5, f"diferencia máxima de {peor:.2f} pp contra la fuente"


def test_sin_errores_de_calidad(con):
    errores = [f for f in run_checks(con) if f[0] == "ERROR"]
    assert not errores, f"controles en rojo: {errores}"


def test_toda_fila_estadistica_tiene_fuente_y_muestra(con):
    for tabla in ("mart_civ_performance", "mart_matchup", "mart_opening"):
        n = con.execute(
            f"SELECT count(*) FROM {tabla} WHERE source_url IS NULL OR n IS NULL OR n <= 0"
        ).fetchone()[0]
        assert n == 0, f"{tabla} tiene {n} filas sin fuente o sin muestra"


def test_civs_nuevas_no_tienen_datos_inventados(con):
    """Mapuche, Muisca y Tupi entraron después del corte: no pueden tener estadística."""
    n = con.execute(
        "SELECT count(*) FROM mart_civ_performance WHERE civ IN ('mapuche', 'muisca', 'tupi')"
    ).fetchone()[0]
    assert n == 0


def test_builds_citan_autor_y_fuente(con):
    n = con.execute(
        "SELECT count(*) FROM ref_build_order WHERE autor IS NULL OR fuente IS NULL"
    ).fetchone()[0]
    assert n == 0


def test_tasas_de_recoleccion_son_las_del_dat(con):
    esperado = {"bayas": 0.31, "ovejas": 0.33, "caza y jabali": 0.41, "madera": 0.39,
                "piedra": 0.36, "oro": 0.38, "granja": 0.53}
    filas = dict(con.execute("SELECT tarea, work_rate FROM ref_gather_rate").fetchall())
    for tarea, valor in esperado.items():
        assert filas[tarea] == pytest.approx(valor, abs=0.001)
