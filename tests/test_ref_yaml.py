"""Los archivos de referencia escritos a mano tienen que ser verificables contra el juego.

El test central es `test_todo_bono_esta_en_el_texto_oficial`: cada `texto_en` del YAML debe
aparecer literalmente en la descripción de la civ que trae el juego. Es lo que hace imposible
que se cuele un bono inventado o mal recordado.
"""

from __future__ import annotations

import re

import pytest
import yaml

from aoe2coach.config import DB_PATH, REF
from aoe2coach.db import connect

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="falta correr la ingesta")


@pytest.fixture(scope="module")
def con():
    c = connect(read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def bonos():
    return yaml.safe_load((REF / "civ_bonuses.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def estrategias():
    return yaml.safe_load((REF / "strategies.yaml").read_text(encoding="utf-8"))


def _normalizar(t: str) -> str:
    """Compara sin ruido: espacios colapsados, sin viñetas ni saltos."""
    return re.sub(r"\s+", " ", (t or "").replace("•", " ")).strip().lower()


def test_todo_bono_esta_en_el_texto_oficial(con, bonos):
    faltantes = []
    for civ, data in bonos["civs"].items():
        fila = con.execute("SELECT bonos_texto_en FROM ref_civ WHERE civ = ?", [civ]).fetchone()
        assert fila, f"la civ {civ} del YAML no existe en el tech tree"
        oficial = _normalizar(fila[0])
        for bono in data["bonos"]:
            if _normalizar(bono["texto_en"]) not in oficial:
                faltantes.append(f"{civ}: {bono['texto_en']}")
    assert not faltantes, "bonos que NO figuran en el texto del juego:\n  " + "\n  ".join(faltantes)


def test_las_civs_modeladas_son_las_mas_jugadas(con, bonos):
    """Si el YAML modela una civ marginal y deja afuera una top, algo se desalineó."""
    top = {
        c[0]
        for c in con.execute(
            "SELECT civ FROM mart_civ_performance "
            "WHERE map = 'all' AND elo_bucket = 'all' ORDER BY play_rate DESC LIMIT 16"
        ).fetchall()
    }
    modeladas = set(bonos["civs"])
    cubiertas = len(top & modeladas)
    assert cubiertas >= 12, f"sólo {cubiertas}/16 del top están modeladas: faltan {top - modeladas}"


def test_efectos_referencian_tareas_y_unidades_que_existen(con, bonos):
    tareas = {t[0] for t in con.execute("SELECT tarea FROM ref_gather_rate").fetchall()}
    problemas = []
    for civ, data in bonos["civs"].items():
        for bono in data["bonos"]:
            ef = bono.get("efecto") or {}
            if bono["tipo"] == "gather_rate" and ef.get("tarea") not in tareas:
                problemas.append(f"{civ}: tarea desconocida {ef.get('tarea')!r}")
    assert not problemas, problemas


def test_estrategias_apuntan_a_aperturas_que_existen(con, estrategias):
    reales = {o[0] for o in con.execute("SELECT DISTINCT opening FROM mart_opening").fetchall()}
    problemas = []
    for e in estrategias["estrategias"]:
        for ap in [e["apertura_pulse"], *e.get("aperturas_relacionadas", [])]:
            if ap not in reales:
                problemas.append(f"{e['id']}: apertura inexistente {ap!r}")
    assert not problemas, problemas


def test_estrategias_apuntan_a_openings_historicos_que_existen(con, estrategias):
    reales = {o[0] for o in con.execute(
        "SELECT DISTINCT opening FROM mart_uptime_historico"
    ).fetchall()}
    problemas = [
        f"{e['id']}: opening_2023 inexistente {e['opening_2023']!r}"
        for e in estrategias["estrategias"]
        if e["opening_2023"] not in reales
    ]
    assert not problemas, problemas


def test_cada_estrategia_tiene_al_menos_un_build(con, estrategias):
    sin_build = []
    for e in estrategias["estrategias"]:
        patron = " OR ".join(["lower(nombre) LIKE ?"] * len(e["patrones_build"]))
        n = con.execute(
            f"SELECT count(*) FROM ref_build_order WHERE {patron}",
            [f"%{p.lower()}%" for p in e["patrones_build"]],
        ).fetchone()[0]
        if n == 0:
            sin_build.append(e["id"])
    assert not sin_build, f"estrategias sin ningún build order que las ejecute: {sin_build}"


def test_favorece_referencia_estrategias_reales(bonos, estrategias):
    ids = {e["id"] for e in estrategias["estrategias"]}
    problemas = [
        f"{civ}: {b['texto_en'][:40]}… favorece {sorted(set(b.get('favorece', [])) - ids)}"
        for civ, data in bonos["civs"].items()
        for b in data["bonos"]
        if set(b.get("favorece", [])) - ids
    ]
    assert not problemas, problemas
