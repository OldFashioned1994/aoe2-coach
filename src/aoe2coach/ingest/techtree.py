"""Ingesta de aoe2techtree (MIT): costos, HP, ataque, armaduras y tiempos exactos.

Fuente: https://github.com/SiegeEngineers/aoe2techtree

Lo que este repo NO trae es el efecto numérico de los bonos de civilización: `civs.<Civ>.meta`
viene vacío y el bono sólo existe como texto en los locales. Ese texto se guarda igual —es la
cita oficial que acompaña a cada bono modelado a mano en `data/ref/civ_bonuses.yaml`.
"""

from __future__ import annotations

import html
import re
from typing import Iterator

from aoe2coach.config import TECHTREE_DATA, TECHTREE_STRINGS, TECHTREE_TREE
from aoe2coach.ingest.http import fetch_json, meta_of

ARCHIVO_DATA = "techtree_data.json"


def download(*, force: bool = False) -> dict:
    return fetch_json(TECHTREE_DATA, ARCHIVO_DATA, force=force)


def download_strings(lang: str = "es", *, force: bool = False) -> dict:
    return fetch_json(
        TECHTREE_STRINGS.format(lang=lang), f"techtree_strings_{lang}.json", force=force
    )


def source() -> tuple[str, str]:
    m = meta_of(ARCHIVO_DATA)
    return m.get("url") or TECHTREE_DATA, m.get("fetched_at") or ""


def _texto(raw: str | None) -> str:
    """Los strings del juego traen <br>, <b> y entidades HTML."""
    if not raw:
        return ""
    limpio = re.sub(r"<br\s*/?>", "\n", raw)
    limpio = re.sub(r"<[^>]+>", "", limpio)
    return html.unescape(limpio).strip()


def _costo(cost: dict | None, recurso: str) -> int:
    return int((cost or {}).get(recurso, 0))


def rows_units(data: dict, strings: dict) -> Iterator[dict]:
    # Los nombres de unidad no están en el strings.json del repo (falta el id 5083 del Archer,
    # por ejemplo), así que casi siempre queda el nombre interno. Los nombres legibles salen de
    # data/ref/unidades_alias.yaml.
    for uid, u in data["data"]["Unit"].items():
        yield {
            "id": int(uid),
            "internal_name": u.get("internal_name"),
            "nombre": (_texto(strings.get(str(u.get("LanguageNameId"))))
                       or u.get("internal_name")),
            "food": _costo(u.get("Cost"), "Food"),
            "wood": _costo(u.get("Cost"), "Wood"),
            "gold": _costo(u.get("Cost"), "Gold"),
            "stone": _costo(u.get("Cost"), "Stone"),
            "hp": u.get("HP"),
            "attack": u.get("Attack"),
            "melee_armor": u.get("MeleeArmor"),
            "pierce_armor": u.get("PierceArmor"),
            "range": u.get("Range"),
            "reload_time": u.get("ReloadTime"),
            "attack_delay": u.get("AttackDelaySeconds"),
            "accuracy": u.get("AccuracyPercent"),
            "speed": u.get("Speed"),
            "line_of_sight": u.get("LineOfSight"),
            "train_time": u.get("TrainTime"),
            # Los bonos de daño por clase de armadura: acá se define un counter de verdad.
            "attacks_json": _json(u.get("Attacks")),
            "armours_json": _json(u.get("Armours")),
        }


def rows_techs(data: dict, strings: dict, strings_en: dict | None = None) -> Iterator[dict]:
    strings_en = strings_en or {}
    for tid, t in data["data"]["Tech"].items():
        yield {
            "id": int(tid),
            "internal_name": t.get("internal_name"),
            # Varias tecnologías no tienen cadena en el locale español: se cae al inglés
            # antes que dejar el nombre vacío.
            "nombre": (_texto(strings.get(str(t.get("LanguageNameId"))))
                       or _texto(strings_en.get(str(t.get("LanguageNameId"))))
                       or t.get("internal_name")),
            "food": _costo(t.get("Cost"), "Food"),
            "wood": _costo(t.get("Cost"), "Wood"),
            "gold": _costo(t.get("Cost"), "Gold"),
            "stone": _costo(t.get("Cost"), "Stone"),
            "research_time": t.get("ResearchTime"),
            "repeatable": bool(t.get("Repeatable", False)),
        }


#: En los árboles por civ, cada nodo trae su estado. Sólo uno significa "no lo tenés".
_NO_DISPONIBLE = "NotAvailable"


def download_tree(civ_en: str, *, force: bool = False) -> dict:
    """Árbol de una civ. OJO: las listas `civs.<Civ>.Unit` de data.json NO sirven para esto.

    Ahí figuran nodos que la civ no tiene (en Godos aparecen unidades marcadas luego como
    NotAvailable), porque describen qué se dibuja en el árbol, no qué está habilitado. El dato
    real es `node_status` de estos archivos.
    """
    return fetch_json(
        TECHTREE_TREE.format(civ=civ_en.upper()), f"techtree_tree_{civ_en.lower()}.json",
        force=force,
    )


def rows_civ_tech_tree(civ_en: str, arbol: dict) -> Iterator[dict]:
    """Un nodo por fila, con si la civ lo tiene o no."""
    for nodo in arbol.get("units_techs", []):
        if nodo.get("node_id") is None:
            continue
        yield {
            "civ": civ_en.lower(),
            "tipo": (nodo.get("node_type") or "").lower(),
            "id": int(nodo["node_id"]),
            "nombre_nodo": nodo.get("name"),
            "disponible": nodo.get("node_status") != _NO_DISPONIBLE,
        }


def rows_buildings(data: dict, strings: dict) -> Iterator[dict]:
    for bid, b in data["data"]["Building"].items():
        yield {
            "id": int(bid),
            "internal_name": b.get("internal_name"),
            "nombre": _texto(strings.get(str(b.get("LanguageNameId")))),
            "food": _costo(b.get("Cost"), "Food"),
            "wood": _costo(b.get("Cost"), "Wood"),
            "gold": _costo(b.get("Cost"), "Gold"),
            "stone": _costo(b.get("Cost"), "Stone"),
            "hp": b.get("HP"),
            "build_time": b.get("TrainTime"),
        }


def rows_civs(data: dict, strings: dict, strings_en: dict | None = None) -> Iterator[dict]:
    strings_en = strings_en or {}
    for nombre_en, c in data["civs"].items():
        yield {
            "civ": nombre_en.lower(),
            "nombre_en": nombre_en,
            "nombre_es": _texto(strings.get(str(c.get("name_string_id")))),
            "era": c.get("era"),
            # Cita oficial de los bonos: es la fuente que acompaña a cada bono modelado.
            # Se guarda también el inglés porque la traducción es ambigua justo donde importa
            # (p. ej. "recolectores" traduce "foragers", que son sólo los de bayas).
            "bonos_texto": _texto(strings.get(str(c.get("help_string_id")))),
            "bonos_texto_en": _texto(strings_en.get(str(c.get("help_string_id")))),
            "n_units": len(c.get("Unit") or []),
            "n_techs": len(c.get("Tech") or []),
            "n_buildings": len(c.get("Building") or []),
        }


def _json(v) -> str | None:
    import json

    return None if v is None else json.dumps(v, separators=(",", ":"))
