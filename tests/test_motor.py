"""Tests del motor de recomendación.

Lo que se controla acá no es "que recomiende X" —eso cambia con los pesos y con los datos—
sino las propiedades que no pueden romperse: que todo número tenga evidencia, que el puntaje
sea la suma de sus componentes, que el mapa condicione la respuesta y que nunca se afirme algo
sobre una civ sin datos.
"""

from __future__ import annotations

import pytest

from aoe2coach.config import DB_PATH
from aoe2coach.db import connect
from aoe2coach.engine import evidencia as ev
from aoe2coach.engine.modelos import Contexto
from aoe2coach.engine.motor import puntuar, recomendar
from aoe2coach.engine.presentacion import render_texto

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="falta correr la ingesta")


@pytest.fixture(scope="module")
def con():
    c = connect(read_only=True)
    yield c
    c.close()


def test_el_puntaje_es_la_suma_de_sus_componentes(con):
    perfil = ev.perfil_mapa(con, "arabia")
    for e in puntuar(con, Contexto(civ="franks", mapa="arabia", elo=1100), "med_low", perfil):
        assert e.score == pytest.approx(sum(c.puntos for c in e.componentes), abs=0.01)


def test_todo_componente_estadistico_trae_evidencia_con_n(con):
    perfil = ev.perfil_mapa(con, "arabia")
    for e in puntuar(con, Contexto(civ="franks", mapa="arabia", elo=1100), "med_low", perfil):
        for c in e.componentes:
            if c.evidencia is not None:
                assert c.evidencia.n and c.evidencia.n > 0
                assert c.evidencia.fuente
                assert c.evidencia.ci is not None


def test_el_mapa_cambia_la_recomendacion(con):
    """Arena es cerrado y Arabia abierto: el scout rush no puede rankear igual en los dos."""
    abierto = puntuar(con, Contexto(civ="franks", mapa="arabia", elo=1100), "med_low",
                      ev.perfil_mapa(con, "arabia"))
    cerrado = puntuar(con, Contexto(civ="franks", mapa="arena", elo=1100), "med_low",
                      ev.perfil_mapa(con, "arena"))
    pos_arabia = [e.id for e in abierto].index("scouts")
    pos_arena = [e.id for e in cerrado].index("scouts")
    assert pos_arabia < pos_arena, "el scout rush debería caer en el ranking al pasar a Arena"


def test_la_estrategia_incompatible_con_el_mapa_recibe_su_penalizacion(con):
    cerrado = puntuar(con, Contexto(civ="franks", mapa="arena", elo=1100), "med_low",
                      ev.perfil_mapa(con, "arena"))
    scouts = next(e for e in cerrado if e.id == "scouts")
    assert any(c.nombre == "el mapa no acompaña" and c.puntos < 0 for c in scouts.componentes)


def test_dificultad_penaliza_solo_en_tramos_bajos(con):
    perfil = ev.perfil_mapa(con, "arabia")
    bajo = puntuar(con, Contexto(civ="franks", mapa="arabia", elo=900), "low", perfil)
    alto = puntuar(con, Contexto(civ="franks", mapa="arabia", elo=1900), "high", perfil)
    drush_bajo = next(e for e in bajo if e.id == "drush_fc")
    drush_alto = next(e for e in alto if e.id == "drush_fc")
    assert any(c.nombre == "dificultad de ejecución" for c in drush_bajo.componentes)
    assert not any(c.nombre == "dificultad de ejecución" for c in drush_alto.componentes)


def test_evidencia_degradada_se_penaliza_y_se_avisa(con):
    """Un dato de 'todos los mapas' no puede pasar por dato del mapa pedido."""
    perfil = ev.perfil_mapa(con, "arena")
    for e in puntuar(con, Contexto(civ="turks", mapa="arena", elo=1500), "med_high", perfil):
        degradado = [c for c in e.componentes if c.nombre == "el dato no es de tu contexto"]
        ap = next((c for c in e.componentes if c.nombre == "win rate de la apertura"), None)
        if degradado:
            assert degradado[0].puntos < 0
            assert "en todos los mapas" in ap.detalle


def test_civ_sin_datos_avisa_y_no_inventa(con):
    """Mapuche entró después del corte: no puede aparecer un win rate suyo."""
    r = recomendar(con, Contexto(civ="mapuche", mapa="arabia", elo=1100))
    assert any("no tiene ninguna estadística" in a for a in r.advertencias)
    for e in r.analisis_matchup.values():
        assert e.valor is None or e.n, "un valor sin muestra no puede mostrarse"


def test_el_reporte_siempre_advierte_del_patch(con):
    r = recomendar(con, Contexto(civ="franks", mapa="arabia", elo=1100))
    assert any("162286" in a and "177723" in a for a in r.advertencias)


def test_el_build_cita_autor_y_fuente(con):
    r = recomendar(con, Contexto(civ="franks", mapa="arabia", elo=1100))
    assert r.build is not None
    assert r.build.autor and r.build.fuente
    assert r.build.pasos


def test_los_calculos_declaran_supuestos_y_formula(con):
    r = recomendar(con, Contexto(civ="franks", mapa="arabia", elo=1100))
    assert r.calculos
    for c in r.calculos:
        assert c.formula and c.fuente and c.supuestos


def test_render_sin_civ_muestra_el_ranking_de_civs(con):
    """Sin civ elegida, el reporte ahora sugiere cuál usar en vez de dejar el hueco."""
    texto = render_texto(recomendar(con, Contexto(mapa="arabia", elo=1100)))
    assert "ESTRATEGIA RECOMENDADA" in texto
    assert "QUÉ CIV ELEGIR" in texto
    assert "Se arma el plan con" in texto


def test_counters_clasicos_salen_de_la_aritmetica(con):
    """Si estos tres se rompen, el modelo de daño dejó de reflejar el juego."""
    from aoe2coach.engine.aritmetica import costo_efectividad

    for unidad, contra in (("piquero", "caballero"), ("escaramuzador", "arquero"),
                           ("caballero", "arquero")):
        c = costo_efectividad(con, unidad, contra)
        assert c and c.resultado.startswith(unidad), f"{unidad} debería ganarle a {contra}"


def test_sugerir_civs_ordena_por_dato_medido(con):
    """El ranking de civs no puede favorecer a las que tienen bonos modelados.

    Sólo 16 de 53 están modeladas: si la afinidad sumara puntos, esas 16 treparían por un
    sesgo del proyecto y no por rendir mejor.
    """
    from aoe2coach.engine.motor import sugerir_civs

    civs = sugerir_civs(con, Contexto(mapa="arabia", elo=500), "low", "scouts")
    assert civs, "debería haber civs sugeridas"
    pisos = [
        next(c.evidencia.ci[0] for c in civ.componentes if c.evidencia)
        for civ in civs
    ]
    assert pisos == sorted(pisos, reverse=True), "el orden no sigue al dato medido"
    for civ in civs:
        afinidad = [c for c in civ.componentes if "acompaña el plan" in c.nombre]
        assert all(c.puntos == 0 for c in afinidad), "la afinidad no debe sumar puntos acá"


def test_sugerir_civs_excluye_las_que_no_tienen_datos(con):
    from aoe2coach.config import CIVS_SIN_DATOS, CIVS_SIN_DATOS_EN_FUENTE
    from aoe2coach.engine.motor import sugerir_civs

    sugeridas = {c.civ for c in sugerir_civs(con, Contexto(mapa="arabia", elo=500), "low", None, top=60)}
    assert not (sugeridas & (CIVS_SIN_DATOS | CIVS_SIN_DATOS_EN_FUENTE))


def test_sin_civ_el_reporte_elige_una_y_arma_el_plan(con):
    r = recomendar(con, Contexto(mapa="arabia", elo=500))
    assert r.civs_sugeridas
    assert r.contexto.civ == r.civs_sugeridas[0].civ, "el plan debe armarse con la civ elegida"
    assert r.build is not None
