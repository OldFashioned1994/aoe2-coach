"""Descarga con caché en disco.

Todo lo que baja de la red queda guardado en `data/raw/` junto a un sidecar `.meta.json`
con URL, fecha y tamaño. Dos motivos: la app funciona offline con el último snapshot, y
cualquier número que muestre se puede rastrear hasta el archivo que lo originó.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from aoe2coach.config import RAW, USER_AGENT

TIMEOUT = httpx.Timeout(60.0, read=300.0)


def _meta_path(dest: Path) -> Path:
    return dest.with_suffix(dest.suffix + ".meta.json")


def fetch(url: str, dest_name: str, *, force: bool = False, params: dict | None = None) -> Path:
    """Baja `url` a `data/raw/<dest_name>` si no está en caché. Devuelve la ruta."""
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / dest_name
    if dest.exists() and not force:
        return dest

    with httpx.Client(
        timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}, http2=False
    ) as client:
        with client.stream("GET", url, params=params) as resp:
            resp.raise_for_status()
            final_url = str(resp.url)
            tmp = dest.with_suffix(dest.suffix + ".part")
            digest = hashlib.md5()
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1 << 16):
                    fh.write(chunk)
                    digest.update(chunk)
            tmp.replace(dest)

    _meta_path(dest).write_text(
        json.dumps(
            {
                "url": final_url,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "bytes": dest.stat().st_size,
                "md5": digest.hexdigest(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return dest


def fetch_json(url: str, dest_name: str, *, force: bool = False, params: dict | None = None) -> Any:
    path = fetch(url, dest_name, force=force, params=params)
    return json.loads(path.read_text(encoding="utf-8"))


def meta_of(dest_name: str) -> dict:
    """Metadatos de una descarga: de dónde salió y cuándo. Se propaga a las tablas."""
    p = _meta_path(RAW / dest_name)
    if not p.exists():
        return {"url": None, "fetched_at": None}
    return json.loads(p.read_text(encoding="utf-8"))
