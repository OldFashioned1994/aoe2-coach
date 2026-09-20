"""Estadística: intervalos de confianza y niveles de confianza.

Regla del proyecto: ninguna proporción se muestra sin su n y su intervalo. Calculamos el
intervalo nosotros con Wilson score aunque la fuente ya traiga uno, para que el criterio sea
uniforme entre aoestats y AoE Pulse y sea auditable.
"""

from __future__ import annotations

import math
from typing import Literal

Confianza = Literal["alta", "media", "baja", "sin_datos"]

#: z de la normal para 95 % (dos colas).
Z95 = 1.959963984540054


def wilson(wins: int, n: int, z: float = Z95) -> tuple[float, float, float]:
    """Intervalo de Wilson al 95 %. Devuelve (proporción, límite inferior, límite superior).

    Se elige Wilson sobre el intervalo normal porque no se rompe con n chico ni con
    proporciones cerca de 0 o 1, que es justo donde caen los matchups poco jugados.
    """
    if n <= 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / denom
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = max(0.0, centro - margen)
    high = min(1.0, centro + margen)
    # Con wins = 0 o wins = n el límite da exactamente 0 o 1 en teoría, pero en coma flotante
    # queda a un ulp del otro lado y dejaría a p fuera de su propio intervalo.
    return (p, min(low, p), max(high, p))


def confianza(n: int, *, patch_vigente: bool = False) -> Confianza:
    """Nivel de confianza de un dato, por reglas fijas (ver docs/design.md §6.1).

    Mientras no haya datos del patch que corre el juego, el techo es "media": un n enorme de
    un patch viejo no vuelve actual a un número viejo.
    """
    if n <= 0:
        return "sin_datos"
    if n < 200:
        return "baja"
    if n >= 2000 and patch_vigente:
        return "alta"
    return "media"


def margen_pp(low: float, high: float) -> float:
    """Semiancho del intervalo en puntos porcentuales, para mostrar `51,4 % ± 0,4`."""
    return (high - low) / 2 * 100


def diferencia_significativa(
    wins_a: int, n_a: int, wins_b: int, n_b: int, z: float = Z95
) -> bool:
    """¿Dos proporciones difieren de verdad? Test de dos proporciones.

    Se usa para no afirmar que una estrategia es mejor que otra cuando los intervalos se
    superponen sin más.
    """
    if n_a <= 0 or n_b <= 0:
        return False
    p_a, p_b = wins_a / n_a, wins_b / n_b
    p_pool = (wins_a + wins_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        return False
    return abs(p_a - p_b) / se > z
