"""Tests de la capa estadística: es donde un error se propaga a todas las recomendaciones."""

from __future__ import annotations

import pytest

from aoe2coach.transform.stats import (
    confianza,
    diferencia_significativa,
    margen_pp,
    wilson,
)


def test_wilson_valores_conocidos():
    # Caso real: Francos en Arabia, patch 162286 (aoestats publica 51,40 % [50,97 – 51,83]).
    p, low, high = wilson(26688, 51920)
    assert p == pytest.approx(0.5140, abs=0.0001)
    assert low == pytest.approx(0.5097, abs=0.0005)
    assert high == pytest.approx(0.5183, abs=0.0005)


def test_wilson_no_se_rompe_con_muestra_chica():
    # Con n=1 y una victoria, el intervalo tiene que ser ancho pero válido: el intervalo
    # normal daría [1, 1], que es la clase de número que no queremos mostrar nunca.
    p, low, high = wilson(1, 1)
    assert p == 1.0
    assert low < 0.3
    assert high == pytest.approx(1.0, abs=1e-9)


def test_wilson_dentro_de_rango():
    for wins, n in [(0, 10), (10, 10), (5, 10), (1, 1000), (999, 1000)]:
        p, low, high = wilson(wins, n)
        assert 0.0 <= low <= p <= high <= 1.0


def test_wilson_sin_muestra():
    assert wilson(0, 0) == (0.0, 0.0, 0.0)


def test_intervalo_se_angosta_con_mas_muestra():
    _, l1, h1 = wilson(51, 100)
    _, l2, h2 = wilson(5100, 10000)
    assert (h2 - l2) < (h1 - l1)


def test_confianza_por_reglas():
    assert confianza(0) == "sin_datos"
    assert confianza(199) == "baja"
    assert confianza(200) == "media"
    # n grande pero patch viejo: sigue siendo "media". Es la regla que evita vender como
    # sólido un número de un patch que ya no se juega.
    assert confianza(100_000, patch_vigente=False) == "media"
    assert confianza(100_000, patch_vigente=True) == "alta"


def test_margen_en_puntos_porcentuales():
    assert margen_pp(0.5097, 0.5183) == pytest.approx(0.43, abs=0.01)


def test_diferencia_significativa():
    # 54,3 % (n=103.672) vs 46,8 % (n=67.000): Scouts contra Range Opener en Arabia.
    assert diferencia_significativa(56294, 103672, 31356, 67000)
    # Misma diferencia aparente, muestras minúsculas: no alcanza para afirmar nada.
    assert not diferencia_significativa(11, 20, 9, 20)
    assert not diferencia_significativa(1, 0, 1, 10)
