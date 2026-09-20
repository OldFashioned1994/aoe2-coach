-- Limpieza de los dumps de aoestats (ver docs/design.md §5).
-- Los placeholders {matches} y {players} se reemplazan por listas de archivos Parquet.

CREATE OR REPLACE TABLE raw_matches AS
SELECT
    map,
    started_timestamp,
    -- OJO: `duration` viene en NANOsegundos (mediana ≈ 2,68e12 = 44,6 min), no en segundos
    -- como sugiere la documentación de aoestats. Se normaliza acá.
    duration / 1e9 AS duration_s,
    game_id,
    avg_elo,
    num_players,
    replay_enhanced,
    leaderboard,
    mirror,
    patch,
    game_type,
    game_speed,
    starting_age,
    regexp_extract(filename, 'dump_matches_([0-9-]+)_', 1) AS semana
FROM read_parquet({matches}, union_by_name = true, filename = true);

CREATE OR REPLACE TABLE raw_players AS
SELECT
    game_id,
    civ,
    winner,
    team,
    -- `opening` es VARCHAR en los dumps de 2023 y INTEGER en los de 2026 (viene todo en NULL),
    -- así que se castea siempre o el union falla.
    CAST(opening AS VARCHAR) AS opening,
    feudal_age_uptime,
    castle_age_uptime,
    imperial_age_uptime,
    old_rating,
    new_rating,
    profile_id
FROM read_parquet({players}, union_by_name = true);

-- Partidas utilizables: 1v1 Random Map rankeado, sin espejos, sin basura.
-- Los filtros replican los criterios que declara aoestats en su FAQ y agregan el descarte de
-- partidas con cantidad impar de jugadores, que su propio scrubbing deja pasar.
CREATE OR REPLACE VIEW clean_matches_1v1 AS
SELECT *
FROM raw_matches
WHERE leaderboard = 'random_map'
  AND num_players = 2
  AND num_players % 2 = 0
  AND NOT mirror
  AND duration_s BETWEEN 300 AND 10800
  AND game_type = 'random_map'
  AND map IS NOT NULL;

CREATE OR REPLACE VIEW clean_players_1v1 AS
SELECT p.*, m.map, m.patch, m.duration_s, m.semana, m.avg_elo
FROM raw_players p
JOIN clean_matches_1v1 m USING (game_id);
