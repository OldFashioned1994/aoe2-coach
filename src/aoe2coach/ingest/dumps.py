"""Dumps semanales de aoestats en Parquet — nivel partida.

Los agregados del motor salen de `/api/stats/`; estos dumps son para lo que esa API no da:

1. **Corpus histórico de ejecución** (semanas de 2023): uptimes reales a Feudal/Castillos y la
   apertura detectada por jugador. Es lo único que existe con esa granularidad — el campo se
   dejó de completar entre marzo y junio de 2024 (ver research §1.5).
2. Análisis propios a nivel partida que no estén precalculados.

Por defecto se bajan pocas semanas: cada una pesa entre 2 y 5 MB por archivo y son 200+.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aoe2coach.config import AOESTATS_BASE, AOESTATS_DUMPS
from aoe2coach.ingest.http import fetch, fetch_json

#: Semanas con `replay_enhanced` en alta proporción: el corpus de uptimes sale de acá.
#: Verificado por muestreo: en may-2023 el 93,5 % de las partidas trae datos de replay.
SEMANAS_CON_REPLAY = ("2023-05-07", "2023-04-02", "2023-06-04", "2023-07-02")


@dataclass(frozen=True)
class Dump:
    start_date: str
    end_date: str
    num_matches: int
    num_players: int
    matches_url: str
    players_url: str

    @property
    def rango(self) -> str:
        return f"{self.start_date}_{self.end_date}"


def listar(*, force: bool = False) -> list[Dump]:
    """Dumps con datos. Los publicados vacíos (desde feb-2026) se descartan acá."""
    data = fetch_json(AOESTATS_DUMPS, "aoestats_db_dumps.json", force=force)
    filas = data["db_dumps"] if isinstance(data, dict) and "db_dumps" in data else data
    return [
        Dump(
            start_date=d["start_date"],
            end_date=d["end_date"],
            num_matches=d["num_matches"],
            num_players=d["num_players"],
            matches_url=d["matches_url"],
            players_url=d["players_url"],
        )
        for d in filas
        if d.get("num_matches", 0) > 0 and d.get("matches_url")
    ]


def ultimas(n: int = 4, *, force: bool = False) -> list[Dump]:
    return sorted(listar(force=force), key=lambda d: d.start_date, reverse=True)[:n]


def con_replay(*, force: bool = False) -> list[Dump]:
    todos = {d.start_date: d for d in listar(force=force)}
    return [todos[s] for s in SEMANAS_CON_REPLAY if s in todos]


def descargar(dump: Dump, *, force: bool = False) -> tuple[Path, Path]:
    m = fetch(AOESTATS_BASE + dump.matches_url, f"dump_matches_{dump.rango}.parquet", force=force)
    p = fetch(AOESTATS_BASE + dump.players_url, f"dump_players_{dump.rango}.parquet", force=force)
    return m, p
