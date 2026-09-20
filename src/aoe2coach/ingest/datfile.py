"""Tasas de recolección, extraídas del .dat del juego.

Fuente: https://github.com/hszemi/aoe2dat (`data/full.json.xz`, volcado directo del .dat).
⚠️ El repo no declara licencia: lo usamos como referencia y NO redistribuimos su archivo. De
ahí que este módulo destile un JSON propio y chico (`data/ref/gather_rates.json`) con los
valores que necesitamos y su procedencia; el .xz queda en `data/raw/`, que no se versiona.

`Bird.WorkRate` es la tasa BRUTA de la tarea. La tasa efectiva es menor: hay que descontar
caminata al depósito y capacidad de carga. El motor usa la bruta sólo para amortizaciones
relativas (donde la caminata se cancela entre las dos ramas de la comparación) y lo aclara.
"""

from __future__ import annotations

import json
import lzma
from pathlib import Path

from aoe2coach.config import DATFILE_FULL, REF
from aoe2coach.ingest.http import fetch, meta_of

ARCHIVO = "aoe2dat_full.json.xz"
DESTILADO = REF / "gather_rates.json"

#: Unidades-tarea del aldeano. El nombre interno es estable entre versiones del .dat.
TAREAS = {
    "VMFOR": ("bayas", "food"),
    "VMSHE": ("ovejas", "food"),
    "VMHUN": ("caza y jabali", "food"),
    "VMFAR": ("granja", "food"),
    "VMFIS": ("pesca", "food"),
    "VMLUM": ("madera", "wood"),
    # Son dos unidades distintas con tasas distintas: el oro se pica más rápido
    # (0,38) que la piedra (0,36). Tratarlas como una sola es un error.
    "VMMIN": ("piedra", "stone"),
    "VMGLD": ("oro", "gold"),
}


def download(*, force: bool = False) -> Path:
    return fetch(DATFILE_FULL, ARCHIVO, force=force)


def destilar(*, force: bool = False) -> dict:
    """Extrae las tasas base y las guarda en `data/ref/gather_rates.json` (versionable)."""
    path = download(force=force)
    data = json.loads(lzma.open(path).read())

    # Civ 1 = British: sin bonos económicos, así que sus valores son los base del juego.
    civ = data["Civs"][1]
    por_nombre = {u["Name"]: u for u in civ["Units"] if u}

    tasas = {}
    for interno, (tarea, recurso) in TAREAS.items():
        u = por_nombre.get(interno)
        if not u:
            continue
        tasas[tarea] = {
            "unidad_interna": interno,
            "recurso": recurso,
            "work_rate": (u.get("Bird") or {}).get("WorkRate"),
            "speed": u.get("Speed"),
            # La capacidad de carga NO se puede leer de `ResourceStorages` en este volcado:
            # los Amount que trae (1 / -1) son flags, no unidades de recurso. Antes que
            # publicar un 1 falso, queda en null hasta tener una fuente que la confirme.
            "capacidad": None,
        }

    meta = meta_of(ARCHIVO)
    salida = {
        "_fuente": {
            "url": meta.get("url") or DATFILE_FULL,
            "fetched_at": meta.get("fetched_at"),
            "civ_referencia": civ.get("Name"),
            "nota": (
                "WorkRate bruto del .dat, sin descontar caminata ni capacidad de carga. "
                "La granja tiene mecanica propia: su tasa efectiva es bastante menor."
            ),
        },
        "tasas": tasas,
    }
    REF.mkdir(parents=True, exist_ok=True)
    DESTILADO.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    return salida


def cargar() -> dict:
    """Lee el destilado; si no existe, lo genera."""
    if not DESTILADO.exists():
        return destilar()
    return json.loads(DESTILADO.read_text(encoding="utf-8"))


# --- Efectos de las tecnologías sobre la recolección --------------------------

#: En el .dat, un EffectCommand `Type = 5` multiplica un atributo de una unidad. El atributo 13
#: es el WorkRate. Así, Double-Bit Axe aparece como "multiplicar por 1.2 el WorkRate del
#: leñador": el número exacto del juego, sin depender de ninguna wiki.
_TYPE_MULTIPLICAR_ATRIBUTO = 5
_ATRIBUTO_WORK_RATE = 13

DESTILADO_EFECTOS = REF / "tech_effects_eco.json"


def destilar_efectos_eco(*, force: bool = False) -> dict:
    """Extrae qué tecnología multiplica la tasa de qué aldeano, y por cuánto."""
    path = download(force=force)
    data = json.loads(lzma.open(path).read())
    civ = data["Civs"][1]

    # Mapa id → (nombre interno, tarea legible). Se arma desde el .dat: nada hardcodeado.
    por_id: dict[int, tuple[str, str]] = {}
    for u in civ["Units"]:
        if not u:
            continue
        nombre = u.get("Name") or ""
        if len(nombre) >= 5 and nombre[0] == "V" and nombre[1] in "MF":
            interno_masculino = "VM" + nombre[2:5]
            tarea = TAREAS.get(interno_masculino, (None, None))[0]
            if tarea:
                por_id[u["ID"]] = (nombre, tarea)

    efectos: dict[str, dict] = {}
    for e in data["Effects"]:
        nombre = e.get("Name") or ""
        for c in e.get("EffectCommands") or []:
            if (
                c.get("Type") == _TYPE_MULTIPLICAR_ATRIBUTO
                and c.get("C") == _ATRIBUTO_WORK_RATE
                and c.get("A") in por_id
                and c.get("D")
                and c["D"] != 1
            ):
                unidad, tarea = por_id[c["A"]]
                clave = f"{nombre}|{tarea}"
                efectos[clave] = {
                    "tech": nombre,
                    "tarea": tarea,
                    "unidad_interna": unidad,
                    "multiplicador": c["D"],
                }

    meta = meta_of(ARCHIVO)
    salida = {
        "_fuente": {
            "url": meta.get("url") or DATFILE_FULL,
            "fetched_at": meta.get("fetched_at"),
            "nota": (
                "EffectCommands Type=5 (multiplicar atributo) sobre el atributo 13 (WorkRate) "
                "de las unidades-tarea del aldeano. Valores exactos del .dat."
            ),
        },
        "efectos": sorted(efectos.values(), key=lambda x: (x["tarea"], x["tech"])),
    }
    REF.mkdir(parents=True, exist_ok=True)
    DESTILADO_EFECTOS.write_text(
        json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return salida


def cargar_efectos_eco() -> dict:
    if not DESTILADO_EFECTOS.exists():
        return destilar_efectos_eco()
    return json.loads(DESTILADO_EFECTOS.read_text(encoding="utf-8"))
