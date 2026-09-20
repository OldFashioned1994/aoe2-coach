"""Tests del parseo de las fuentes, con payloads sintéticos (no tocan la red)."""

from __future__ import annotations

from aoe2coach.config import elo_bucket
from aoe2coach.ingest import aoepulse, aoestats, builds

PAYLOAD = [
    {
        "patch": 162286,
        "grouping": "random_map",
        "elo_grouping": "all",
        "total_games": 1000,
        "civ_stats": {
            "franks": {
                "rank": 19,
                "prior_rank": 22,
                "wins": 50,
                "num_games": 100,
                "win_rate": 0.5,
                "ci_lower": 0.4,
                "ci_upper": 0.6,
                "play_rate": 0.05,
                "avg_game_length": 2589,
                "by_map": {
                    "arabia": {"wins": 30, "num_games": 50, "win_rate": 0.6,
                               "ci_lower": 0.45, "ci_upper": 0.74, "play_rate": 0.5},
                    # Entrada vacía con el centinela de aoestats: no debe entrar.
                    "nomad": {"wins": 0, "num_games": 0, "win_rate": 0.0,
                              "ci_lower": -1.0, "ci_upper": -1.0, "play_rate": 0.0},
                },
                "by_matchup": {
                    "goths": {"wins": 6, "num_games": 10, "win_rate": 0.6,
                              "ci_lower": 0.3, "ci_upper": 0.83, "play_rate": 0.1},
                },
                "by_opening": {
                    "scouts": {"wins": 0, "num_games": 0, "win_rate": 0.0,
                               "ci_lower": -1.0, "ci_upper": -1.0, "play_rate": 0.0},
                },
                "by_game_time": {
                    "long": {"wins": 20, "num_games": 40, "win_rate": 0.5,
                             "ci_lower": 0.35, "ci_upper": 0.65, "play_rate": 0.4},
                },
            }
        },
        "map_stats": {"arabia": {"num_games": 500, "play_rate": 0.5, "by_civ": {}}},
        "opening_stats": {},
    }
]


def test_aoestats_descarta_entradas_vacias():
    filas = list(aoestats.rows_civ_performance(PAYLOAD))
    mapas = {f["map"] for f in filas}
    assert "arabia" in mapas
    assert "nomad" not in mapas, "las entradas con centinela -1.0 no deben cargarse"
    assert "all" in mapas, "falta el agregado de todos los mapas"


def test_aoestats_matchup_y_duracion():
    mu = list(aoestats.rows_matchup(PAYLOAD))
    assert mu == [
        {"patch": 162286, "elo_bucket": "all", "n": 10, "wins": 6, "play_rate": 0.1,
         "src_win_rate": 0.6, "src_ci_low": 0.3, "src_ci_high": 0.83,
         "civ": "franks", "opp_civ": "goths"}
    ]
    dur = list(aoestats.rows_by_duration(PAYLOAD))
    assert dur[0]["duration_bucket"] == "long" and dur[0]["n"] == 40


def test_pulse_descarta_espejos_y_parsea_matchups():
    data = {
        "openings_list": [
            {"name": "Scouts Any vs Scouts Any", "wins": -1, "total": 100},
            {"name": "Scouts Any vs Range Opener Any", "wins": 60, "total": 100},
        ]
    }
    filas = list(aoepulse.rows_opening_matchups(data, "Arabia", "med_low"))
    assert len(filas) == 1
    assert filas[0]["opening"] == "Scouts Any"
    assert filas[0]["opp_opening"] == "Range Opener Any"
    assert filas[0]["map"] == "arabia"


def test_pulse_openings_usa_wins_mas_losses():
    data = {"openings_list": [{"name": "Scouts Any", "wins": 60, "losses": 40, "total": 999}]}
    fila = next(iter(aoepulse.rows_openings(data, "Arabia", "all")))
    assert fila["n"] == 100, "n se recalcula: el campo `total` de Pulse no es wins+losses"


def test_builds_traduce_iconos_y_parsea_tiempos():
    """Los marcadores de ícono tienen que volverse palabras legibles, no restos del archivo."""
    nota = "Build 2 @other/House_aoe2DE.webp@ | First 6 @resource/MaleVillDE.webp@ to sheep"
    limpia = builds.limpiar_nota(nota)
    assert "@" not in limpia
    assert "casa" in limpia and "aldeanos" in limpia
    assert "House" not in limpia and "MaleVill" not in limpia

    # Un ícono que no esté en el diccionario se muestra igual, sin inventar traducción.
    assert "inventado" in builds.limpiar_nota("x @otro/Inventado_aoe2DE.webp@")
    assert builds._tiempo_a_segundos("2:30") == 150
    assert builds._tiempo_a_segundos(None) is None
    assert builds._tiempo_a_segundos("raro") is None


def test_elo_bucket_sin_solapamiento():
    assert elo_bucket(999) == "low"
    assert elo_bucket(1000) == "med_low"
    assert elo_bucket(1199) == "med_low"
    assert elo_bucket(1200) == "medium"
    assert elo_bucket(1800) == "high"
    assert elo_bucket(3500) == "high"
