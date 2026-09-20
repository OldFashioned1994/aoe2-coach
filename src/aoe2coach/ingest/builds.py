"""Ingesta de build orders documentados.

Fuente: https://github.com/CraftySalamander/rtsbuilds (GPL-3.0) — el catálogo que alimenta
RTS Overlay y buildorderguide.com. Cada build trae `author` y `source`, y los mostramos
siempre: es la condición para usarlos.

No entra material de pago (la guía de Hera es un PDF de Patreon). Si el usuario compró una, la
puede dejar en `data/builds/propios/` y se carga igual, pero no se versiona.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from aoe2coach.config import BUILDS, RTSBUILDS_RAW, RTSBUILDS_TREE
from aoe2coach.ingest.http import fetch_json

PREFIJO = "docs/api/builds/aoe2/"
#: Los pasos traen marcadores de ícono tipo @resource/MaleVillDE.webp@.
_ICONO = re.compile(r"@([^@]+)@")


def listar_remotos() -> list[str]:
    tree = fetch_json(RTSBUILDS_TREE, "rtsbuilds_tree.json", force=True)
    return sorted(
        n["path"] for n in tree["tree"]
        if n["path"].startswith(PREFIJO) and n["path"].endswith(".json")
    )


def descargar_todos(*, force: bool = False) -> list[Path]:
    BUILDS.mkdir(parents=True, exist_ok=True)
    destinos = []
    for path in listar_remotos():
        nombre = path.rsplit("/", 1)[-1]
        destino = BUILDS / nombre
        if destino.exists() and not force:
            destinos.append(destino)
            continue
        data = fetch_json(RTSBUILDS_RAW.format(path=path), f"rtsbuild_{nombre}", force=force)
        data["_source_repo"] = "https://github.com/CraftySalamander/rtsbuilds (GPL-3.0)"
        destino.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        destinos.append(destino)
    return destinos


_ALIAS_ICONOS: dict[str, str] | None = None


def alias_iconos() -> dict[str, str]:
    """Traducción de los íconos del build a palabras (data/ref/iconos_alias.yaml)."""
    global _ALIAS_ICONOS
    if _ALIAS_ICONOS is None:
        import yaml

        from aoe2coach.config import REF

        datos = yaml.safe_load((REF / "iconos_alias.yaml").read_text(encoding="utf-8"))
        _ALIAS_ICONOS = {k.lower(): v for k, v in datos["iconos"].items()}
    return _ALIAS_ICONOS


def _clave_icono(archivo: str) -> str:
    """`resource/MaleVillDE.webp` → `malevill`, para poder buscarlo en el diccionario."""
    base = archivo.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    base = re.sub(r"(_alpha|_aoe2de|_aoe2DE|DE)$", "", base, flags=re.IGNORECASE)
    return base.strip("_").lower()


def limpiar_nota(texto: str) -> str:
    """Reemplaza los marcadores de ícono por su palabra en español.

    Lo que no está en el diccionario se muestra con su nombre original: preferimos que se lea
    raro antes que inventar una traducción que cambie el sentido del paso.
    """
    def _reemplazo(m: re.Match) -> str:
        clave = _clave_icono(m.group(1))
        return alias_iconos().get(clave, clave.replace("_", " "))

    return re.sub(r"\s{2,}", " ", _ICONO.sub(_reemplazo, texto)).strip()


def _tiempo_a_segundos(t: str | None) -> int | None:
    if not t or ":" not in t:
        return None
    m, s = t.split(":", 1)
    try:
        return int(m) * 60 + int(s)
    except ValueError:
        return None


def leer_locales() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(BUILDS.glob("*.json"))
    ] + [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((BUILDS / "propios").glob("*.json"))
        if (BUILDS / "propios").exists()
    ]


def rows_build_orders(builds: list[dict]) -> Iterator[dict]:
    for b in builds:
        pasos = b.get("build_order") or []
        yield {
            "build_id": _slug(b.get("name", "sin-nombre")),
            "nombre": b.get("name"),
            "civ": (b.get("civilization") or "Generic").lower(),
            "autor": b.get("author"),
            "fuente": b.get("source"),
            "repo": b.get("_source_repo"),
            "n_pasos": len(pasos),
            "villagers_final": max((p.get("villager_count", 0) or 0) for p in pasos) if pasos else 0,
            "duracion_s": max(
                (_tiempo_a_segundos(p.get("time")) or 0) for p in pasos
            ) if pasos else 0,
        }


def rows_build_steps(builds: list[dict]) -> Iterator[dict]:
    for b in builds:
        build_id = _slug(b.get("name", "sin-nombre"))
        for i, p in enumerate(b.get("build_order") or []):
            r = p.get("resources") or {}
            yield {
                "build_id": build_id,
                "paso": i,
                "villager_count": p.get("villager_count"),
                "age": p.get("age"),
                "food": r.get("food"),
                "wood": r.get("wood"),
                "gold": r.get("gold"),
                "stone": r.get("stone"),
                "builder": r.get("builder"),
                "time": p.get("time"),
                "time_s": _tiempo_a_segundos(p.get("time")),
                "notas": " | ".join(limpiar_nota(n) for n in (p.get("notes") or [])),
            }


def _slug(nombre: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-")
    return s or "sin-nombre"
