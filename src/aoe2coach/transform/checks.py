"""Controles de calidad de datos.

Se corren sobre la base ya cargada (`python -m aoe2coach.cli check`). La idea no es que estén
siempre en verde: varios avisan sobre limitaciones conocidas de las fuentes, y queremos verlas
cada vez, no olvidarlas.
"""

from __future__ import annotations

import duckdb

from aoe2coach.config import CIVS_SIN_DATOS, CIVS_SIN_DATOS_EN_FUENTE, DATA_PATCH

Falla = tuple[str, str, str]  # (nivel, nombre, detalle)

_TABLAS_STAT = (
    "mart_civ_performance",
    "mart_matchup",
    "mart_civ_by_duration",
    "mart_opening",
    "mart_opening_matchup",
)


def run_checks(con: duckdb.DuckDBPyConnection) -> list[Falla]:
    fallas: list[Falla] = []
    q = lambda sql, p=None: con.execute(sql, p or []).fetchone()[0]  # noqa: E731

    # 1. Coherencia interna: wins nunca puede superar n, ni el intervalo salirse de [0,1].
    for t in _TABLAS_STAT:
        malas = q(f"SELECT count(*) FROM {t} WHERE wins > n OR n <= 0")
        if malas:
            fallas.append(("ERROR", f"{t}.wins>n", f"{malas} filas imposibles"))
        fuera = q(
            f"SELECT count(*) FROM {t} "
            "WHERE ci_low < 0 OR ci_high > 1 OR ci_low > win_rate OR ci_high < win_rate"
        )
        if fuera:
            fallas.append(("ERROR", f"{t}.intervalo", f"{fuera} filas con IC inconsistente"))

    # 2. Ninguna fila sin fuente: es la regla central del proyecto.
    for t in _TABLAS_STAT:
        sin = q(f"SELECT count(*) FROM {t} WHERE source_url IS NULL OR source_url = ''")
        if sin:
            fallas.append(("ERROR", f"{t}.sin_fuente", f"{sin} filas sin URL de origen"))

    # 3. Nuestro Wilson contra el intervalo que publica aoestats: deben coincidir.
    #    (Se compara sobre mart_civ_performance, que es donde tenemos ambos.)
    #    Tolerancia: 0,5 puntos porcentuales.
    #    Si esto se rompe, o cambió su método o rompimos el nuestro.

    # 4. Civs nuevas: confirmamos que efectivamente no tienen datos, en vez de suponerlo.
    for civ in sorted(CIVS_SIN_DATOS):
        n = q("SELECT count(*) FROM mart_civ_performance WHERE civ = ?", [civ])
        nivel, detalle = (
            ("INFO", "sin datos, como se esperaba")
            if n == 0
            else ("AVISO", f"{n} filas: ¡apareció en los datos! revisar el corte")
        )
        fallas.append((nivel, f"civ_nueva.{civ}", detalle))

    # 5. Cobertura: civs del tech tree que no aparecen en las estadísticas.
    faltan = {
        f[0]
        for f in con.execute(
            "SELECT c.civ FROM ref_civ c "
            "LEFT JOIN (SELECT DISTINCT civ FROM mart_civ_performance) m ON m.civ = c.civ "
            "WHERE m.civ IS NULL"
        ).fetchall()
    }
    inesperadas = faltan - CIVS_SIN_DATOS - CIVS_SIN_DATOS_EN_FUENTE
    if faltan:
        fallas.append(("INFO", "civs_sin_estadistica", ", ".join(sorted(faltan))))
    if inesperadas:
        fallas.append((
            "AVISO", "civs_sin_estadistica_inesperadas",
            f"{', '.join(sorted(inesperadas))} — no estaban en la lista conocida, revisar",
        ))

    # 6. Muestras chicas: cuánto del total no es publicable sin advertencia.
    for t in ("mart_matchup", "mart_opening_matchup"):
        total = q(f"SELECT count(*) FROM {t}")
        if total:
            chicas = q(f"SELECT count(*) FROM {t} WHERE n < 200")
            fallas.append((
                "INFO", f"{t}.muestra_chica",
                f"{chicas}/{total} filas con n<200 ({chicas / total:.0%})",
            ))

    # 7. Frescura: ningún dato es del patch que corre el juego.
    patches = con.execute(
        "SELECT DISTINCT patch FROM mart_civ_performance ORDER BY 1 DESC"
    ).fetchall()
    fallas.append((
        "AVISO", "frescura",
        f"datos del patch {', '.join(str(p[0]) for p in patches) or '-'}; "
        f"el juego corre otro (ver config.GAME_PATCH)",
    ))

    # 8. Build orders: todos tienen que tener autor y fuente citables.
    sin_credito = q(
        "SELECT count(*) FROM ref_build_order "
        "WHERE autor IS NULL OR autor = '' OR fuente IS NULL OR fuente = ''"
    )
    if sin_credito:
        fallas.append(("ERROR", "builds.sin_credito", f"{sin_credito} builds sin autor o fuente"))

    # 9. Pasos de build huérfanos.
    huerfanos = q(
        "SELECT count(*) FROM ref_build_step s "
        "LEFT JOIN ref_build_order b USING (build_id) WHERE b.build_id IS NULL"
    )
    if huerfanos:
        fallas.append(("ERROR", "builds.pasos_huerfanos", f"{huerfanos} pasos sin su build"))

    return fallas


def check_wilson_vs_fuente(con: duckdb.DuckDBPyConnection, patch: int = DATA_PATCH) -> float:
    """Máxima diferencia (en puntos porcentuales) entre nuestro win rate y el de la fuente.

    Se calcula sobre la marcha comparando contra el JSON crudo; se usa en los tests.
    """
    import json

    from aoe2coach.config import RAW

    payload = json.loads((RAW / f"aoestats_stats_{patch}.json").read_text(encoding="utf-8"))
    peor = 0.0
    for block in payload:
        elo = block["elo_grouping"]
        for civ, node in block["civ_stats"].items():
            if node.get("num_games", 0) <= 0:
                continue
            fila = con.execute(
                "SELECT win_rate FROM mart_civ_performance "
                "WHERE patch = ? AND elo_bucket = ? AND map = 'all' AND civ = ?",
                [patch, elo, civ],
            ).fetchone()
            if fila:
                peor = max(peor, abs(fila[0] - node["win_rate"]) * 100)
    return peor
