"""La aritmética del juego: cuentas cerradas con valores exactos, no simulación.

Alcance deliberado (docs/design.md §6.4): amortización de tecnologías, valor económico de un
bono de civilización y costo-efectividad entre unidades. Nada de simular la partida tick a tick
— ahí es donde se producen números lindos y falsos.

Todo lo que se usa acá sale del .dat del juego: tasas de recolección, multiplicadores de las
tecnologías, costos, ataques y armaduras por clase.
"""

from __future__ import annotations

import json

import duckdb

import yaml

from aoe2coach.config import REF
from aoe2coach.engine.modelos import Calculo

#: Clases de armadura base del motor Genie: todo ataque tiene una de las dos como componente
#: principal, y los demás pares (clase, monto) son bonos contra tipos de unidad.
CLASE_PIERCE = 3
CLASE_MELEE = 4

FUENTE_DAT = "valores del .dat del juego (aoe2dat) y del tech tree (aoe2techtree)"


_ALIAS: dict[str, str] | None = None


def alias_unidades() -> dict[str, str]:
    """Alias en español → nombre interno (ver data/ref/unidades_alias.yaml)."""
    global _ALIAS
    if _ALIAS is None:
        datos = yaml.safe_load((REF / "unidades_alias.yaml").read_text(encoding="utf-8"))
        _ALIAS = {k.lower(): v for k, v in datos["unidades"].items()}
    return _ALIAS


def nombre_visible(interno: str) -> str:
    """El inverso del alias: para mostrar "caballero" en vez de KNGHT."""
    for es, ref in alias_unidades().items():
        if ref == interno:
            return es
    return interno


def buscar_unidad(con: duckdb.DuckDBPyConnection, texto: str) -> dict | None:
    """Busca por alias en español, nombre interno o coincidencia parcial."""
    t = alias_unidades().get(texto.strip().lower(), texto).strip().lower()
    for consulta, param in (
        ("SELECT * FROM ref_unit WHERE lower(nombre) = ?", t),
        ("SELECT * FROM ref_unit WHERE lower(internal_name) = ?", t),
        ("SELECT * FROM ref_unit WHERE lower(nombre) LIKE ? ORDER BY length(nombre) LIMIT 1",
         f"%{t}%"),
    ):
        cur = con.execute(consulta, [param])
        fila = cur.fetchone()
        if fila:
            return dict(zip([d[0] for d in cur.description], fila))
    return None


def _costo_total(u: dict) -> int:
    return int((u.get("food") or 0) + (u.get("wood") or 0) + (u.get("gold") or 0)
               + (u.get("stone") or 0))


def _costo_texto(u: dict) -> str:
    partes = [f"{int(u[r])} {n}" for r, n in
              (("food", "comida"), ("wood", "madera"), ("gold", "oro"), ("stone", "piedra"))
              if u.get(r)]
    return " + ".join(partes) if partes else "sin costo"


# --- 1. Amortización de una tecnología ---------------------------------------


def amortizacion_tech(
    con: duckdb.DuckDBPyConnection, tech: str, n_aldeanos: int
) -> Calculo | None:
    """¿En cuánto tiempo una tech de recolección devuelve lo que costó?"""
    # El .dat y el tech tree no escriben igual los nombres ("Double-Bit Axe" vs
    # "Double Bit Axe"), así que se comparan sin guiones.
    clave = tech.lower().replace("-", " ")
    efecto = con.execute(
        "SELECT tech, tarea, multiplicador FROM ref_tech_effect "
        "WHERE replace(lower(tech), '-', ' ') = ?",
        [clave],
    ).fetchone()
    if not efecto:
        return None
    nombre_tech, tarea, mult = efecto

    clave_tech = nombre_tech.lower().replace("-", " ")
    costo = con.execute(
        "SELECT nombre, food, wood, gold, stone, research_time FROM ref_tech "
        "WHERE replace(lower(internal_name), '-', ' ') = ? "
        "   OR replace(lower(nombre), '-', ' ') = ?",
        [clave_tech, clave_tech],
    ).fetchone()
    if not costo:
        return None
    nombre_es, food, wood, gold, stone, research_time = costo

    tasa = con.execute(
        "SELECT work_rate, recurso FROM ref_gather_rate WHERE tarea = ?", [tarea]
    ).fetchone()
    if not tasa:
        return None
    work_rate, recurso = tasa

    ganancia_por_segundo = n_aldeanos * work_rate * (mult - 1)
    if ganancia_por_segundo <= 0:
        return None

    costo_del_recurso = {"wood": wood, "gold": gold, "stone": stone, "food": food}.get(recurso, 0)
    costo_total = food + wood + gold + stone
    # Si la tech se paga con el mismo recurso que mejora, la amortización es directa. Si no,
    # se compara contra el costo total y hay que decirlo, porque mezcla recursos distintos.
    mismo_recurso = costo_del_recurso == costo_total and costo_total > 0
    segundos = costo_total / ganancia_por_segundo

    supuestos = [
        f"{n_aldeanos} aldeanos en {tarea} durante todo el período",
        "tasa bruta del .dat, sin descontar caminata al depósito ni capacidad de carga",
        f"no incluye los {research_time:.0f} s que tarda la investigación",
    ]
    if not mismo_recurso:
        supuestos.append(
            "la tech se paga con recursos distintos del que mejora: la comparación suma "
            "recursos de distinto tipo como si valieran lo mismo"
        )

    return Calculo(
        titulo=f"¿Cuándo se paga {nombre_es or nombre_tech}?",
        resultado=f"{segundos / 60:.1f} min ({segundos:.0f} s) con {n_aldeanos} aldeanos",
        formula=(
            f"{costo_total} recursos ÷ ({n_aldeanos} aldeanos × {work_rate} /s × "
            f"{(mult - 1) * 100:.0f}%) = {segundos:.0f} s"
        ),
        fuente=FUENTE_DAT,
        supuestos=supuestos,
    )


# --- 2. Valor económico de un bono de civilización ----------------------------


def valor_bono_gather(
    con: duckdb.DuckDBPyConnection, tarea: str, multiplicador: float, n_aldeanos: int,
    minutos: float,
) -> Calculo | None:
    tasa = con.execute(
        "SELECT work_rate FROM ref_gather_rate WHERE tarea = ?", [tarea]
    ).fetchone()
    if not tasa:
        return None
    work_rate = tasa[0]
    extra = n_aldeanos * work_rate * (multiplicador - 1) * 60 * minutos
    return Calculo(
        titulo=f"Cuánto vale el bono de {tarea} al minuto {minutos:.0f}",
        resultado=f"+{extra:.0f} recursos acumulados",
        formula=(
            f"{n_aldeanos} aldeanos × {work_rate} /s × {(multiplicador - 1) * 100:.0f}% × "
            f"{minutos:.0f} min = {extra:.0f}"
        ),
        fuente=FUENTE_DAT,
        supuestos=[
            f"{n_aldeanos} aldeanos en {tarea} de forma sostenida desde el minuto 0",
            "tasa bruta, sin caminata: el número real es algo menor",
        ],
    )


# --- 3. Costo-efectividad entre unidades --------------------------------------


def _clases_de(u: dict, campo: str) -> dict[int, int]:
    try:
        return {int(x["Class"]): int(x["Amount"]) for x in json.loads(u.get(campo) or "[]")}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def dano_por_golpe(atacante: dict, defensor: dict) -> tuple[float, str]:
    """Daño real de un golpe, con armadura y bonos por clase. Devuelve (daño, explicación)."""
    ataques = _clases_de(atacante, "attacks_json")
    armaduras_def = _clases_de(defensor, "armours_json")

    es_a_distancia = (atacante.get("range") or 0) > 0
    clase_base = CLASE_PIERCE if es_a_distancia else CLASE_MELEE
    base = ataques.get(clase_base, atacante.get("attack") or 0)
    armadura = (defensor.get("pierce_armor") if es_a_distancia
                else defensor.get("melee_armor")) or 0

    bonos = {
        clase: monto
        for clase, monto in ataques.items()
        if clase not in (CLASE_MELEE, CLASE_PIERCE) and monto > 0 and clase in armaduras_def
    }
    bono_total = sum(bonos.values())
    dano = max(1.0, base - armadura + bono_total)

    detalle = f"{base} de ataque − {armadura} de armadura"
    if bono_total:
        detalle += f" + {bono_total} de bono contra su tipo"
    return dano, detalle


def costo_efectividad(
    con: duckdb.DuckDBPyConnection, unidad_a: str, unidad_b: str
) -> Calculo | None:
    """Compara A contra B: cuánto daño por segundo hace cada uno por recurso invertido."""
    a = buscar_unidad(con, unidad_a)
    b = buscar_unidad(con, unidad_b)
    if not a or not b:
        return None

    nombre_a = nombre_visible(a["internal_name"])
    nombre_b = nombre_visible(b["internal_name"])
    dano_ab, det_ab = dano_por_golpe(a, b)
    dano_ba, det_ba = dano_por_golpe(b, a)
    reload_a = a.get("reload_time") or 1
    reload_b = b.get("reload_time") or 1
    dps_a, dps_b = dano_ab / reload_a, dano_ba / reload_b
    costo_a, costo_b = max(1, _costo_total(a)), max(1, _costo_total(b))

    eficiencia_a = dps_a / costo_a * 100
    eficiencia_b = dps_b / costo_b * 100
    ventaja = eficiencia_a / eficiencia_b if eficiencia_b else float("inf")

    gana = nombre_a if ventaja > 1 else nombre_b
    factor = ventaja if ventaja > 1 else (1 / ventaja if ventaja else 0)

    return Calculo(
        titulo=f"{nombre_a} contra {nombre_b}: cuál rinde más por recurso",
        resultado=(
            f"{gana} rinde {factor:.2f}× más por recurso invertido "
            f"({eficiencia_a:.2f} vs {eficiencia_b:.2f} de daño/s por cada 100 recursos)"
        ),
        formula=(
            f"{nombre_a}: {det_ab} = {dano_ab:.0f} de daño ÷ {reload_a}s = "
            f"{dps_a:.2f} daño/s ÷ {costo_a} recursos ({_costo_texto(a)})\n"
            f"{nombre_b}: {det_ba} = {dano_ba:.0f} de daño ÷ {reload_b}s = "
            f"{dps_b:.2f} daño/s ÷ {costo_b} recursos ({_costo_texto(b)})"
        ),
        fuente=FUENTE_DAT,
        supuestos=[
            "unidades sin mejoras de herrería ni bonos de civilización",
            "combate uno contra uno, sin considerar velocidad, alcance ni cantidad",
            "los recursos se suman sin ponderar: 1 de oro cuenta igual que 1 de comida",
        ],
    )
