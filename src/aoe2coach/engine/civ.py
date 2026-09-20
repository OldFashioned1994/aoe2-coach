"""Ficha de civilización: qué bonos tiene, en qué es fuerte y qué le falta.

Tres capas, como el resto del proyecto:

- **Bonos**: texto oficial del juego, tal cual. No se resume ni se interpreta.
- **Fortalezas**: derivadas de los datos medidos (rendimiento por duración de partida, por mapa
  y contra cada rival), siempre con su n.
- **Carencias**: comparación literal del tech tree de la civ contra la lista de unidades y
  tecnologías que definen un 1v1 (`data/ref/tecnologias_clave.yaml`).
"""

from __future__ import annotations

import re
from functools import lru_cache

import duckdb
import yaml

from aoe2coach.config import DATA_PATCH, REF
from aoe2coach.engine import evidencia as ev
from aoe2coach.engine.modelos import Evidencia

#: Encabezados con los que el juego separa las secciones del texto de ayuda (locale español).
_SECCIONES = ("Unidad única:", "Unidades únicas:", "Tecnologías únicas:", "Bonificación de equipo:")

#: Cómo leer los tramos de duración de aoestats. Los cortes son suyos, no nuestros.
DURACION_ETIQUETAS = {
    "quick": "partidas cortas",
    "medium": "partidas medias",
    "med_long": "partidas largas",
    "long": "partidas muy largas",
}


@lru_cache(maxsize=1)
def claves() -> dict:
    return yaml.safe_load((REF / "tecnologias_clave.yaml").read_text(encoding="utf-8"))


def _lineas(bloque: str) -> list[str]:
    return [
        re.sub(r"^[•·\-\s]+", "", linea).strip()
        for linea in bloque.split("\n")
        if linea.strip()
    ]


def parsear_bonos(texto: str) -> dict:
    """Separa el texto de ayuda del juego en sus secciones, sin reescribir nada."""
    if not texto:
        return {"tipo": "", "bonos": [], "unidad_unica": [], "techs_unicas": [], "equipo": []}

    # Se corta por los encabezados conocidos, quedándose con lo que va después de cada uno.
    posiciones = [(texto.find(s), s) for s in _SECCIONES if texto.find(s) >= 0]
    posiciones.sort()
    corte = posiciones[0][0] if posiciones else len(texto)

    cabecera = _lineas(texto[:corte])
    tipo = cabecera[0] if cabecera else ""
    bonos = cabecera[1:] if len(cabecera) > 1 else []

    secciones: dict[str, list[str]] = {}
    for i, (pos, etiqueta) in enumerate(posiciones):
        fin = posiciones[i + 1][0] if i + 1 < len(posiciones) else len(texto)
        secciones[etiqueta] = _lineas(texto[pos + len(etiqueta):fin])

    return {
        "tipo": tipo,
        "bonos": bonos,
        "unidad_unica": secciones.get("Unidad única:", []) + secciones.get("Unidades únicas:", []),
        "techs_unicas": secciones.get("Tecnologías únicas:", []),
        "equipo": secciones.get("Bonificación de equipo:", []),
    }


def perfil_temporal(con: duckdb.DuckDBPyConnection, civ: str, bucket: str) -> dict:
    """¿Es una civ de partidas cortas o largas? Sale de comparar sus propios tramos.

    Se compara el mejor tramo contra el peor y contra su propio promedio: si la diferencia es
    chica, se dice que es pareja en vez de inventar una personalidad.
    """
    tramos = {
        t: Evidencia(**e) for t, e in ev.por_duracion(con, civ, bucket).items()
    }
    utiles = {t: e for t, e in tramos.items() if e.valor is not None and (e.n or 0) >= 200}
    if not utiles:
        return {"tramos": tramos, "veredicto": None}

    mejor = max(utiles.items(), key=lambda kv: kv[1].valor)
    peor = min(utiles.items(), key=lambda kv: kv[1].valor)
    brecha = (mejor[1].valor - peor[1].valor) * 100

    if brecha < 2:
        veredicto = "rinde parecido en cualquier duración"
    else:
        veredicto = (
            f"rinde mejor en {DURACION_ETIQUETAS.get(mejor[0], mejor[0])} "
            f"({mejor[1].pct}) y peor en {DURACION_ETIQUETAS.get(peor[0], peor[0])} "
            f"({peor[1].pct}): {brecha:.1f} puntos de diferencia"
        )
    return {"tramos": tramos, "veredicto": veredicto, "brecha": brecha}


def _extremos(filas: list[dict], top: int) -> tuple[list[dict], list[dict]]:
    """Mejores y peores, sin que una misma fila caiga en las dos listas.

    Con pocos elementos no tiene sentido partirlos en dos: se devuelven todos como una lista
    sola. Mostrar el mismo mapa en "mejores" y en "peores" es ruido, no información.
    """
    if len(filas) <= top + 1:
        return filas, []
    return filas[:top], filas[-top:][::-1]


def mejores_mapas(
    con: duckdb.DuckDBPyConnection, civ: str, bucket: str, n_min: int = 500, top: int = 4
) -> tuple[list[dict], list[dict]]:
    filas = con.execute(
        "SELECT map, n, win_rate, ci_low, ci_high FROM mart_civ_performance "
        "WHERE patch = ? AND civ = ? AND elo_bucket = ? AND map <> 'all' AND n >= ? "
        "ORDER BY win_rate DESC",
        [DATA_PATCH, civ, bucket, n_min],
    ).fetchall()
    return _extremos(
        [{"mapa": f[0], "n": f[1], "win_rate": f[2], "ci": (f[3], f[4])} for f in filas], top
    )


def matchups_extremos(
    con: duckdb.DuckDBPyConnection, civ: str, bucket: str, n_min: int = 200, top: int = 4
) -> tuple[list[dict], list[dict]]:
    filas = con.execute(
        "SELECT opp_civ, n, win_rate, ci_low, ci_high FROM mart_matchup "
        "WHERE patch = ? AND civ = ? AND elo_bucket = ? AND n >= ? ORDER BY win_rate DESC",
        [DATA_PATCH, civ, bucket, n_min],
    ).fetchall()
    return _extremos(
        [{"civ": f[0], "n": f[1], "win_rate": f[2], "ci": (f[3], f[4])} for f in filas], top
    )


def carencias(con: duckdb.DuckDBPyConnection, civ: str) -> list[dict]:
    """Qué le falta de lo que define un 1v1. Comparación literal contra el tech tree."""
    cfg = claves()
    faltan = []

    # `disponible` sale de `node_status` del árbol oficial de la civ: es el único campo que
    # dice de verdad si la tiene. Las listas de data.json incluyen nodos que no están
    # habilitados (ver ingest/techtree.download_tree).
    no_tiene_u = {
        r[0] for r in con.execute(
            "SELECT u.internal_name FROM ref_civ_tech_tree t JOIN ref_unit u ON u.id = t.id "
            "WHERE t.civ = ? AND t.tipo LIKE '%unit%' AND NOT t.disponible", [civ]
        ).fetchall()
    }
    for item in cfg["unidades"]:
        if item["interno"] in no_tiene_u:
            faltan.append({"que": item["nombre"], "por_que": item["por_que"], "tipo": "unidad"})

    no_tiene_t = {
        r[0] for r in con.execute(
            "SELECT x.internal_name FROM ref_civ_tech_tree t JOIN ref_tech x ON x.id = t.id "
            "WHERE t.civ = ? AND t.tipo IN ('research', 'tech') AND NOT t.disponible", [civ]
        ).fetchall()
    }
    for item in cfg["tecnologias"]:
        if item["interno"] in no_tiene_t:
            faltan.append({"que": item["nombre"], "por_que": item["por_que"], "tipo": "tecnología"})

    return faltan


def ficha(con: duckdb.DuckDBPyConnection, civ: str, bucket: str = "all") -> dict:
    """Todo lo que se sabe de una civ, con la fuente de cada parte."""
    fila = con.execute(
        "SELECT nombre_es, nombre_en, bonos_texto, bonos_texto_en FROM ref_civ WHERE civ = ?",
        [civ],
    ).fetchone()
    if not fila:
        return {}

    nombre_es, nombre_en, texto_es, texto_en = fila
    mejores_m, peores_m = mejores_mapas(con, civ, bucket)
    mejores_mu, peores_mu = matchups_extremos(con, civ, bucket)

    return {
        "civ": civ,
        "nombre": nombre_es or nombre_en,
        "nombre_en": nombre_en,
        "secciones": parsear_bonos(texto_es),
        "texto_en": texto_en,
        "general": Evidencia(**ev.civ_en_mapa(con, civ, "all", bucket)),
        "perfil_temporal": perfil_temporal(con, civ, bucket),
        "mejores_mapas": mejores_m,
        "peores_mapas": peores_m,
        "mejores_matchups": mejores_mu,
        "peores_matchups": peores_mu,
        "carencias": carencias(con, civ),
        "bucket": bucket,
    }


def resumen_corto(con: duckdb.DuckDBPyConnection, civ: str) -> list[str]:
    """Los bonos en una línea cada uno, para mostrar junto a la civ en una lista."""
    fila = con.execute("SELECT bonos_texto FROM ref_civ WHERE civ = ?", [civ]).fetchone()
    return parsear_bonos(fila[0])["bonos"] if fila else []
