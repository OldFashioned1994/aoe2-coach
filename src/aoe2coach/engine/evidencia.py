"""Consultas a la base que devuelven `Evidencia`, nunca números sueltos.

Regla de degradación: si no hay muestra para el corte pedido (mapa + tramo de Elo), se cae al
agregado más general y **se deja constancia en `nota`**. Nunca se devuelve un número más general
haciéndolo pasar por el específico.
"""

from __future__ import annotations

import duckdb

from aoe2coach.config import DATA_PATCH, DATA_PATCH_DATE, GAME_PATCH
from aoe2coach.transform.stats import confianza as nivel_confianza

MUESTRA_MINIMA = 200

FUENTE_AOESTATS = f"aoestats, patch {DATA_PATCH}"
FUENTE_PULSE = f"AoE Pulse, patch {DATA_PATCH}"
FUENTE_CORPUS = "corpus de replays 2023 (aoestats)"

_SIN_DATOS = {"fuente": FUENTE_AOESTATS, "confianza": "sin_datos"}


def _evidencia(fila, fuente: str, nota: str | None = None) -> dict:
    if not fila:
        return {"fuente": fuente, "confianza": "sin_datos", "nota": nota}
    n, wr, low, high = fila
    return {
        "valor": wr,
        "n": n,
        "ci": (low, high),
        "fuente": fuente,
        "fecha_dato": str(DATA_PATCH_DATE),
        "confianza": nivel_confianza(n, patch_vigente=(DATA_PATCH == GAME_PATCH)),
        "nota": nota,
    }


def civ_en_mapa(
    con: duckdb.DuckDBPyConnection, civ: str, mapa: str, elo: str, patch: int = DATA_PATCH
) -> dict:
    """Win rate de la civ en ese mapa y tramo. Degrada a 'todos los mapas' y luego a 'todo Elo'."""
    consulta = (
        "SELECT n, win_rate, ci_low, ci_high FROM mart_civ_performance "
        "WHERE patch = ? AND civ = ? AND map = ? AND elo_bucket = ? AND n >= ?"
    )
    fila = con.execute(consulta, [patch, civ, mapa, elo, MUESTRA_MINIMA]).fetchone()
    if fila:
        return _evidencia(fila, FUENTE_AOESTATS)

    fila = con.execute(consulta, [patch, civ, "all", elo, MUESTRA_MINIMA]).fetchone()
    if fila:
        return _evidencia(fila, FUENTE_AOESTATS, f"sin muestra suficiente en {mapa}: promedio de todos los mapas")

    fila = con.execute(consulta, [patch, civ, mapa, "all", MUESTRA_MINIMA]).fetchone()
    if fila:
        return _evidencia(fila, FUENTE_AOESTATS, "sin muestra en tu tramo de Elo: promedio de todos los tramos")

    return dict(_SIN_DATOS, nota=f"{civ} no tiene partidas registradas en el patch {patch}")


def matchup(
    con: duckdb.DuckDBPyConnection, civ: str, rival: str, elo: str, patch: int = DATA_PATCH
) -> dict:
    """Civ vs civ. aoestats no lo desglosa por mapa: siempre es agregado de todos los mapas."""
    consulta = (
        "SELECT n, win_rate, ci_low, ci_high FROM mart_matchup "
        "WHERE patch = ? AND civ = ? AND opp_civ = ? AND elo_bucket = ?"
    )
    fila = con.execute(consulta, [patch, civ, rival, elo]).fetchone()
    nota = "agregado de todos los mapas: la fuente no desglosa el matchup por mapa"
    if fila and fila[0] >= MUESTRA_MINIMA:
        return _evidencia(fila, FUENTE_AOESTATS, nota)

    fila_all = con.execute(consulta, [patch, civ, rival, "all"]).fetchone()
    if fila_all:
        return _evidencia(
            fila_all, FUENTE_AOESTATS,
            nota + "; y sin muestra en tu tramo de Elo, así que es el promedio de todos",
        )
    return dict(_SIN_DATOS, nota=f"no hay partidas de {civ} contra {rival}")


def por_duracion(
    con: duckdb.DuckDBPyConnection, civ: str, elo: str, patch: int = DATA_PATCH
) -> dict[str, dict]:
    """Win rate por duración: el proxy de si la civ es de early o de late game."""
    filas = con.execute(
        "SELECT duration_bucket, n, win_rate, ci_low, ci_high FROM mart_civ_by_duration "
        "WHERE patch = ? AND civ = ? AND elo_bucket = ?",
        [patch, civ, elo],
    ).fetchall()
    return {f[0]: _evidencia(f[1:], FUENTE_AOESTATS) for f in filas}


def apertura(
    con: duckdb.DuckDBPyConnection, apertura_pulse: str, mapa: str, elo: str,
    patch: int = DATA_PATCH,
) -> dict:
    consulta = (
        "SELECT n, win_rate, ci_low, ci_high FROM mart_opening "
        "WHERE patch = ? AND opening = ? AND map = ? AND elo_bucket = ? AND n >= ?"
    )
    fila = con.execute(consulta, [patch, apertura_pulse, mapa, elo, MUESTRA_MINIMA]).fetchone()
    if fila:
        return _evidencia(fila, FUENTE_PULSE)

    fila = con.execute(consulta, [patch, apertura_pulse, mapa, "all", MUESTRA_MINIMA]).fetchone()
    if fila:
        return _evidencia(fila, FUENTE_PULSE, "sin muestra en tu tramo: promedio de todos los Elo")

    fila = con.execute(consulta, [patch, apertura_pulse, "all", elo, MUESTRA_MINIMA]).fetchone()
    if fila:
        return _evidencia(fila, FUENTE_PULSE, f"sin datos de aperturas en {mapa}: promedio de todos los mapas")

    return dict(_SIN_DATOS, fuente=FUENTE_PULSE, nota=f"sin datos de la apertura {apertura_pulse}")


def apertura_vs_apertura(
    con: duckdb.DuckDBPyConnection, mia: str, rival: str, mapa: str, elo: str,
    patch: int = DATA_PATCH,
) -> dict:
    consulta = (
        "SELECT n, win_rate, ci_low, ci_high FROM mart_opening_matchup "
        "WHERE patch = ? AND opening = ? AND opp_opening = ? AND map = ? AND elo_bucket = ? "
        "AND n >= ?"
    )
    for mapa_q, elo_q, nota in (
        (mapa, elo, None),
        (mapa, "all", "promedio de todos los tramos de Elo"),
        ("all", elo, f"sin muestra en {mapa}: promedio de todos los mapas"),
        ("all", "all", "promedio de todos los mapas y tramos"),
    ):
        fila = con.execute(consulta, [patch, mia, rival, mapa_q, elo_q, 50]).fetchone()
        if fila:
            return _evidencia(fila, FUENTE_PULSE, nota)
    return dict(_SIN_DATOS, fuente=FUENTE_PULSE, nota=f"sin datos de {mia} contra {rival}")


def aperturas_del_rival(
    con: duckdb.DuckDBPyConnection, mapa: str, elo: str, patch: int = DATA_PATCH
) -> list[tuple[str, int]]:
    """Qué se juega en ese mapa, para estimar contra qué te vas a cruzar."""
    filas = con.execute(
        "SELECT opening, n FROM mart_opening "
        "WHERE patch = ? AND map = ? AND elo_bucket = ? AND opening <> 'Unknown' "
        "ORDER BY n DESC",
        [patch, mapa, elo],
    ).fetchall()
    return filas or con.execute(
        "SELECT opening, n FROM mart_opening "
        "WHERE patch = ? AND map = 'all' AND elo_bucket = ? AND opening <> 'Unknown' "
        "ORDER BY n DESC",
        [patch, elo],
    ).fetchall()


def perfil_mapa(con: duckdb.DuckDBPyConnection, mapa: str, patch: int = DATA_PATCH) -> dict:
    fila = con.execute(
        "SELECT perfil, fc_share, n_aperturas, agua, naval_share, n_naval, fuente "
        "FROM mart_map_profile WHERE patch = ? AND map = ?",
        [patch, mapa],
    ).fetchone()
    if not fila:
        return {"mapa": mapa, "perfil": "desconocido", "agua": "desconocido",
                "nota": "el mapa no tiene datos suficientes para perfilarlo"}
    return {
        "mapa": mapa, "perfil": fila[0], "fc_share": fila[1], "n_aperturas": fila[2],
        "agua": fila[3], "naval_share": fila[4], "n_naval": fila[5], "fuente": fila[6],
    }


def uptime_esperado(
    con: duckdb.DuckDBPyConnection, opening_2023: str, mapa: str, elo: str
) -> dict:
    """Uptime a Feudal observado en jugadores reales. Ojo: es del corpus de 2023."""
    consulta = (
        "SELECT sum(n) AS n, "
        "       sum(feudal_p50 * n) / sum(n) AS p50, "
        "       min(feudal_p25) AS p25, max(feudal_p75) AS p75 "
        "FROM mart_uptime_historico "
        "WHERE opening = ? AND map = ? AND elo_bucket = ? "
        "HAVING sum(n) > 0"
    )
    for mapa_q, nota in (
        (mapa, None),
        ("all", f"sin muestra en {mapa}"),
    ):
        fila = con.execute(consulta, [opening_2023, mapa_q, elo]).fetchone()
        if fila:
            n, p50, p25, p75 = fila
            base = "datos de 2023: sirven para saber cómo ejecuta la gente, no cuánto rinde hoy"
            return {
                "valor": p50,
                "n": int(n),
                "ci": (p25, p75) if p25 and p75 else None,
                "fuente": FUENTE_CORPUS,
                "fecha_dato": "2023",
                "confianza": nivel_confianza(int(n)),
                "nota": f"{nota}; {base}" if nota else base,
            }
    return {"fuente": FUENTE_CORPUS, "confianza": "sin_datos",
            "nota": "sin uptimes registrados para esa apertura"}
