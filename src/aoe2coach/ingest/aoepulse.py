"""Ingesta de AoE Pulse — la fuente de aperturas (lo que a aoestats le falta).

API no documentada, descubierta leyendo el bundle del sitio (ver docs/research.md §2). Detalle
clave: los nombres de parámetro que uno esperaría (`map_ids`, `patch_ids`) se ignoran en
silencio; los que funcionan son `include_*_ids`. Verificado el 17-ago-2026.

Caveat conocido: las categorías de apertura se solapan ("Scouts Any" incluye a sus follow-ups) y
la suma de los `total` por apertura no coincide con el `total` global de la respuesta. Por eso
guardamos win rate y n, y NO derivamos play rates de acá hasta aclarar la unidad de conteo.
"""

from __future__ import annotations

from typing import Iterator

from aoe2coach.config import (
    AOEPULSE_INFO,
    AOEPULSE_OPENING_MATCHUPS,
    AOEPULSE_OPENING_WR,
    DATA_PATCH,
    ELO_BUCKET_RANGES,
)
from aoe2coach.ingest.http import fetch_json, meta_of

#: Random Map 1v1 en el catálogo de Pulse (`/api/v1/info/`).
LADDER_RM_1V1 = 3

#: Aperturas agregadas: son las que no se solapan entre sí y cubren el árbol completo.
#: Las "* Any" se guardan igual pero marcadas, para no sumarlas con sus hijas por error.
APERTURAS_AGREGADAS = {
    "Premill Drush Any", "Postmill Drush Any", "MAA Any", "Scouts Any", "Range Opener Any",
}


def download_info(*, force: bool = False) -> dict:
    return fetch_json(AOEPULSE_INFO, "aoepulse_info.json", force=force)


#: aoestats nombra los mapas en snake_case y Pulse en Title Case, así que se normaliza. Estos
#: son los casos que la normalización no resuelve, incluido un typo de aoestats.
ALIAS_MAPAS = {
    "scandanavia": "scandinavia",  # así, con la "a", viene de aoestats
}


def map_ids(info: dict, nombre: str) -> list[int]:
    """Ids de un mapa por nombre. Hay nombres repetidos con más de un id (p. ej. Acropolis)."""
    objetivo = nombre.strip().lower().replace("_", " ")
    objetivo = ALIAS_MAPAS.get(objetivo, objetivo)
    return [
        m["id"] for m in info["maps"] if m["name"].strip().lower().replace("_", " ") == objetivo
    ]


def _params(patch: int, ids_mapa: list[int], elo_bucket: str) -> dict:
    p: dict[str, object] = {
        "include_patch_ids": patch,
        "include_ladder_ids": LADDER_RM_1V1,
    }
    if ids_mapa:
        p["include_map_ids"] = ",".join(str(i) for i in ids_mapa)
    if elo_bucket != "all":
        # Los dos límites van siempre juntos: la API rechaza con 400 varios rangos sueltos o
        # con cortes intermedios (ver config.ELO_BUCKET_RANGES).
        lo, hi = ELO_BUCKET_RANGES[elo_bucket]
        p["min_elo"] = lo
        p["max_elo"] = hi
    return p


def _slug(mapa: str, elo: str) -> str:
    return f"{mapa.lower().replace(' ', '-')}_{elo}"


def download_openings(
    info: dict, mapa: str, elo_bucket: str, patch: int = DATA_PATCH, *, force: bool = False
) -> tuple[dict, str]:
    archivo = f"aoepulse_openings_{patch}_{_slug(mapa, elo_bucket)}.json"
    data = fetch_json(
        AOEPULSE_OPENING_WR, archivo, force=force,
        params=_params(patch, map_ids(info, mapa), elo_bucket),
    )
    return data, archivo


def download_opening_matchups(
    info: dict, mapa: str, elo_bucket: str, patch: int = DATA_PATCH, *, force: bool = False
) -> tuple[dict, str]:
    archivo = f"aoepulse_matchups_{patch}_{_slug(mapa, elo_bucket)}.json"
    data = fetch_json(
        AOEPULSE_OPENING_MATCHUPS, archivo, force=force,
        params=_params(patch, map_ids(info, mapa), elo_bucket),
    )
    return data, archivo


def rows_openings(data: dict, mapa: str, elo_bucket: str, patch: int = DATA_PATCH) -> Iterator[dict]:
    for o in data.get("openings_list", []):
        wins, losses = o.get("wins") or 0, o.get("losses") or 0
        n = wins + losses
        if n <= 0 or wins < 0:
            continue
        yield {
            "patch": patch,
            "elo_bucket": elo_bucket,
            "map": mapa.lower(),
            "opening": o["name"],
            "n": n,
            "wins": wins,
        }


def rows_opening_matchups(
    data: dict, mapa: str, elo_bucket: str, patch: int = DATA_PATCH
) -> Iterator[dict]:
    """`name` viene como "A vs B"; en los espejos `wins` es -1 y se descartan."""
    for o in data.get("openings_list", []):
        # En los espejos `wins` viene -1, y en combinaciones sin partidas puede venir null.
        wins, total = o.get("wins"), o.get("total") or 0
        if wins is None or wins < 0 or total <= 0 or " vs " not in o.get("name", ""):
            continue
        izq, der = o["name"].split(" vs ", 1)
        yield {
            "patch": patch,
            "elo_bucket": elo_bucket,
            "map": mapa.lower(),
            "opening": izq.strip(),
            "opp_opening": der.strip(),
            "n": total,
            "wins": wins,
        }


def source_of(archivo: str) -> tuple[str, str]:
    m = meta_of(archivo)
    return m.get("url") or AOEPULSE_OPENING_WR, m.get("fetched_at") or ""
