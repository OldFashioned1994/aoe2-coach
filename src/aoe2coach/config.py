"""Rutas, constantes y catálogos fijos del proyecto.

Todo lo que sea "de dónde salen los datos" vive acá, para que ninguna URL quede
enterrada en el medio del código.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
REF = DATA / "ref"
BUILDS = DATA / "builds"
DB_PATH = DATA / "aoe2coach.duckdb"
SQL_DIR = Path(__file__).resolve().parent / "transform" / "sql"

USER_AGENT = "aoe2coach/0.1 (proyecto personal, uso no comercial)"

# --- Fuentes -----------------------------------------------------------------

AOESTATS_BASE = "https://aoestats.io"
AOESTATS_PATCHES = f"{AOESTATS_BASE}/api/patches/"
AOESTATS_STATS = f"{AOESTATS_BASE}/api/stats/"
AOESTATS_DUMPS = f"{AOESTATS_BASE}/api/db_dumps"

AOEPULSE_BASE = "https://www.aoepulse.com"
AOEPULSE_INFO = f"{AOEPULSE_BASE}/api/v1/info/"
AOEPULSE_OPENING_WR = f"{AOEPULSE_BASE}/api/v1/opening_win_rates/"
AOEPULSE_OPENING_MATCHUPS = f"{AOEPULSE_BASE}/api/v1/opening_matchups/"
AOEPULSE_CIV_WR = f"{AOEPULSE_BASE}/api/v1/civ_win_rates/"

TECHTREE_DATA = (
    "https://raw.githubusercontent.com/SiegeEngineers/aoe2techtree/master/data/data.json"
)
TECHTREE_STRINGS = (
    "https://raw.githubusercontent.com/SiegeEngineers/aoe2techtree/master/data/locales/"
    "{lang}/strings.json"
)
DATFILE_FULL = "https://raw.githubusercontent.com/hszemi/aoe2dat/master/data/full.json.xz"

RTSBUILDS_TREE = (
    "https://api.github.com/repos/CraftySalamander/rtsbuilds/git/trees/HEAD?recursive=1"
)
RTSBUILDS_RAW = "https://raw.githubusercontent.com/CraftySalamander/rtsbuilds/HEAD/{path}"

# --- Estado del ecosistema (ver docs/research.md) -----------------------------

#: Último patch con datos estadísticos. Todo lo posterior no tiene cobertura.
DATA_PATCH = 162286
DATA_PATCH_DATE = date(2025, 12, 2)
#: Última semana de partidas ingeridas por aoestats.
DATA_CUTOFF = date(2026, 2, 7)
#: Patch que corre el juego hoy (actualizar a mano cuando salga uno nuevo).
GAME_PATCH = 177723
GAME_PATCH_DATE = date(2026, 6, 2)

#: Civs sin ningún dato estadístico: entraron con el DLC del 17-feb-2026.
CIVS_SIN_DATOS = {"mapuche", "muisca", "tupi"}
#: Civs que aoestats lista pero con 0 partidas en el patch 162286 (verificado en el payload).
#: A efectos del motor son también "sin datos", aunque existan en el juego desde antes.
CIVS_SIN_DATOS_EN_FUENTE = {"khitans", "jurchens"}
#: El rework del 169123 cambió a los Incas y todo el combate naval.
CIVS_REWORK_POST_DATOS = {"incas"}

ELO_BUCKETS = ("all", "low", "med_low", "medium", "med_high", "high")
#: Tramos de Elo, en semántica [desde, hasta). aoestats define sus buckets por percentiles
#: (0-25 / 25-50 / 50-75 / 75-100 / 99-100, ver su FAQ) pero no publica los cortes; estos
#: umbrales son nuestros y son los que además acepta la API de AoE Pulse, que rechaza con 400
#: varios rangos aparentemente válidos (verificado: 0-1000, 1000-1200, 1200-1400, 1400-1800 y
#: 1800-3000 funcionan; 500-999 no).
ELO_BUCKET_RANGES = {
    "low": (0, 1000),
    "med_low": (1000, 1200),
    "medium": (1200, 1400),
    "med_high": (1400, 1800),
    "high": (1800, 3000),
}

LEADERBOARD_1V1_RM = "random_map"


def elo_bucket(elo: int) -> str:
    """Mapea un Elo a su tramo, en semántica [desde, hasta). Se le muestra al usuario."""
    for name, (lo, hi) in ELO_BUCKET_RANGES.items():
        if lo <= elo < hi:
            return name
    return "high" if elo >= 3000 else "all"


def ensure_dirs() -> None:
    for d in (RAW, REF, BUILDS):
        d.mkdir(parents=True, exist_ok=True)
