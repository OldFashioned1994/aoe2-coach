# AoE2 Coach — Investigación de fuentes (Fase 0)

**Fecha de verificación: 17 de agosto de 2026.** Todo lo que sigue fue probado contra el
endpoint o el archivo real, no tomado de documentación. Cada dato lleva su URL y, cuando es
estadístico, su tamaño de muestra.

---

## 0. Resumen ejecutivo — los 4 hallazgos que condicionan el proyecto

1. **Todo el ecosistema estadístico de AoE2 está congelado en el patch 162286 (2-dic-2025).**
   aoestats dejó de ingerir partidas el **7-feb-2026** y AoE Pulse tampoco tiene patches
   posteriores. No es una elección nuestra: es el estado del ecosistema.
2. **El juego siguió avanzando: el patch vigente es 177723 (2-jun-2026)**, y en el medio salió
   **169123 (17-feb-2026)** con el DLC *The Last Chieftains* (3 civs nuevas: Mapuche, Muisca,
   Tupi), rework de Incas y **overhaul de combate naval**. O sea: los datos disponibles son de
   **10 días antes** del cambio de balance más grande del año.
   → La app tiene que declarar el desfasaje en pantalla, no disimularlo.
3. **Sí existe una API pública no documentada de agregados en aoestats**
   (`/api/stats/?patch=…&grouping=…&elo_grouping=…`) que devuelve win rate, IC al 95 %, n,
   play rate, **by_map**, **by_matchup (civ vs civ)** y **by_game_time**. Es la mejor fuente
   para el motor y evita reprocesar 33 millones de partidas.
4. **Los datos de *comportamiento* (uptimes a Feudal/Castillos, aperturas, qué se investigó en
   cada edad) sólo existen hasta marzo de 2024** en los dumps de aoestats, y en AoE Pulse hasta
   el patch 162286. Para timings actuales hay que parsear replays propios (Fase 4).

---

## 1. aoestats.io — estadísticas agregadas de partidas reales

Sitio: <https://aoestats.io/> · API: <https://aoestats.io/api-info/> · FAQ: <https://aoestats.io/faq>

### 1.1 Qué es y de dónde saca los datos

Agrega partidas rankeadas de AoE2 DE desde los *relic community endpoints* (los mismos que
documenta LibreMatch, <https://wiki.librematch.org/>). La base declara **32.979.710 partidas**
al 17-ago-2026. Reglas de inclusión declaradas en el FAQ:

- Duración in-game entre 5 y 180 minutos.
- Sólo partidas rankeadas; se excluyen desconexiones.
- Se excluyen partidas espejo (todos con la misma civ).
- Se excluyen jugadores "one trick pony" (100+ partidas con 80 %+ en una sola civ).

Licencia: contenido bajo las *Game Content Usage Rules* de Microsoft; parte del material deriva
de Liquipedia (CC BY-SA 3.0). No hay rate limit documentado.

### 1.2 Dumps semanales en Parquet — verificado

`GET https://aoestats.io/api/db_dumps` → 207 entradas. Campos: `start_date`, `end_date`,
`num_matches`, `num_players`, `matches_url`, `players_url`, `match_checksum`, `player_checksum`.

| Hecho verificado | Valor |
|---|---|
| Primer dump | semana del 2022-08-28 |
| Último dump **con datos** | 2026-02-01 → 2026-02-07 (118.661 partidas, 417.903 filas de jugador) |
| Semanas vacías | 29 consecutivas, desde 2026-02-08 hasta 2026-08-09 |
| Tamaño `matches.parquet` de feb-2026 | 2.689.342 bytes |
| Tamaño `matches.parquet` de ago-2026 | 9.378 bytes (archivo existe pero está vacío) |

URL de descarga: `https://aoestats.io/media/db_dumps/date_range%3D<inicio>_<fin>/matches.parquet`
(idem `players.parquet`).

### 1.3 Esquema real de los Parquet (leído con DuckDB, no de la doc)

**matches.parquet** (17 columnas)

| Columna | Tipo | Nota |
|---|---|---|
| `map` | VARCHAR | nombre normalizado en minúscula (`arabia`, `arena`…) |
| `started_timestamp` | TIMESTAMPTZ | |
| `duration` | BIGINT | **nanosegundos** in-game, no segundos: la mediana da 2,68e12 ≈ 44,6 min. La doc de aoestats lo llama "timestamp" y es fácil leerlo mal — filtrar por `duration BETWEEN 300 AND 10800` devuelve cero filas |
| `irl_duration` | BIGINT | ídem, tiempo real (no está en la doc oficial) |
| `game_id` | VARCHAR | clave de join |
| `avg_elo` | DOUBLE | |
| `num_players` | BIGINT | |
| `team_0_elo` / `team_1_elo` | DOUBLE | |
| `replay_enhanced` | BOOLEAN | ver 1.5 |
| `leaderboard` | VARCHAR | ver valores abajo |
| `mirror` | BOOLEAN | |
| `patch` | BIGINT | inferido por aoestats |
| `raw_match_type` | BIGINT | |
| `game_type` | VARCHAR | `random_map`, `empire_wars`… |
| `game_speed` | VARCHAR | |
| `starting_age` | VARCHAR | |

**players.parquet** (13 columnas): `winner`, `game_id`, `team`, `feudal_age_uptime`,
`castle_age_uptime`, `imperial_age_uptime`, `old_rating`, `new_rating`, `match_rating_diff`,
`replay_summary_raw`, `profile_id`, `civ`, `opening`.

> ⚠️ **Trampa de tipos**: en el dump de 2026, `opening` viene como INTEGER porque está 100 % en
> NULL; en los dumps de 2023 es VARCHAR. Cualquier lectura multi-semana tiene que castear
> explícitamente o DuckDB falla al unir.

### 1.4 Cómo se filtra 1v1 Random Map (verificado sobre feb-2026)

`leaderboard` **no** vale `rm_1v1`. Los valores reales y su frecuencia en esa semana:

| leaderboard | partidas |
|---|---|
| `random_map` | 69.768 |
| `team_random_map` | 45.826 |
| `co_random_map` | 1.950 |
| `co_team_random_map` | 1.117 |

→ 1v1 RM = `leaderboard = 'random_map' AND num_players = 2` (71.718 filas... ojo: 71.718 es el
total de partidas con 2 jugadores incluyendo otros leaderboards; el cruce hay que hacerlo con
las dos condiciones).

**Datos sucios confirmados**: distribución de `num_players` en la semana → 2: 71.718 · 4: 20.765 ·
6: 9.008 · **7: 1** · 8: 17.169. La partida de 7 jugadores es exactamente la basura que advierte
el FAQ. La limpieza de la Fase 1 tiene que descartar `num_players` impares.

### 1.5 Los datos de replay se cortaron en 2024 — verificado por muestreo

Descargué 6 semanas repartidas y conté `replay_enhanced`:

| Semana | Partidas | Con replay |
|---|---|---|
| 2023-05-07 | 240.425 | 224.756 (93,5 %) |
| 2023-11-05 | 216.884 | 11.059 (5,1 %) |
| 2024-03-03 | 237.859 | 16.999 (7,1 %) |
| 2024-06-02 | 219.935 | **0** |
| 2024-11-03 | 217.117 | **0** |
| 2025-09-07 | 175.178 | **0** |
| 2026-02-01 | 118.661 | **0** |

Es decir: **uptimes y aperturas sólo existen en datos de 2023 y principios de 2024**, con
balance completamente distinto al actual.

Lo que sí traen esos dumps viejos es riquísimo. `opening` en la semana 2023-05-07 (417 k filas):

| opening | n |
|---|---|
| fast_castle | 198.526 |
| unknown | 191.373 |
| archers | 108.882 |
| scouts | 105.312 |
| man_at_arms | 65.563 |
| (null) | 62.443 |
| trash | 54.895 |
| fires | 21.075 |
| drush | 14.386 |
| galleys | 12.713 |
| towers | 7.736 |

Y `replay_summary_raw` es un JSON por jugador con, para cada edad: `uptime`, lista de
`research`, `unit_counts` y `building_counts`. Ejemplo real (recortado):

```json
{"age_stats": {"dark": {"uptime": 0, "research": ["feudal age"],
  "unit_counts": {"villager": 32},
  "building_counts": {"farm": 8, "mill": 1, "house": 7, "barracks": 1,
                      "lumber camp": 2, "mining camp": 2}},
 "feudal": {"uptime": 796.753, "research": ["castle age", "gold mining"], ...}}}
```

**Uso previsto**: no para recomendar meta actual, sino como *corpus histórico de ejecución* —
distribución empírica de uptimes por Elo, orden real en que los jugadores investigan techs, y
validación del simulador económico contra comportamiento humano.

### 1.6 La API de agregados (no documentada) — la joya

```
GET https://aoestats.io/api/patches/
GET https://aoestats.io/api/stats/?patch=162286&grouping=random_map&elo_grouping=all
```

`/api/patches/` devuelve 19 patches con `number`, `label`, `release_date`, `url` (link a las
notas oficiales), `description` y `total_games`. Los últimos:

| patch | fecha | partidas | descripción |
|---|---|---|---|
| 162286 | 2025-12-02 | 1.787.254 | red bull Londinium |
| 153015 | 2025-08-12 | 3.225.748 | Pathing changes |
| 147949 | 2025-06-25 | 3.045.391 | Khitans nerf |
| 143421 | 2025-05-07 | 2.188.996 | The Three Kingdoms |

> El total del patch 162286 (1,79 M) coincide con ~10 semanas × ~180 k de los dumps: confirma que
> la ingesta murió el 7-feb-2026 y que el sitio muestra datos congelados aunque su pie diga
> "Stats last updated: 2026-08-17".

`/api/stats/` **sin filtros pesa más de 72 MB y la conexión se corta**. Con filtros baja a
6,7 MB y responde bien. Devuelve 6 filas (una por bucket de Elo):

| elo_grouping | partidas 1v1 RM |
|---|---|
| all | 1.027.074 |
| low | 252.755 |
| med_low | 180.656 |
| medium | 261.219 |
| med_high | 332.444 |
| high | 27.229 |

Cada fila trae `civ_stats` (50 civs), `map_stats` (21 mapas), `opening_stats` y `total_games`.
Por civ: `rank`, `prior_rank`, `wins`, `num_games`, `win_rate`, `ci_lower`, `ci_upper`,
`play_rate`, `avg_game_length`, `avg_feudal_time`, `avg_castle_time`, `avg_imperial_time`,
y los diccionarios `by_map`, `by_matchup`, `by_opening`, `by_game_time`.

Ejemplo real (Francos, patch 162286, 1v1 RM, todos los Elo):

- Global: **50,20 %** [49,90 – 50,51], n = 101.233, play rate 4,93 %, rank 19 (venía 22).
- En Arabia: **51,40 %** [50,97 – 51,83], n = 51.920 (el 51,3 % de las partidas de Francos).
- Por duración: partidas largas 51,98 % (n = 44.229) vs. partidas cortas 42,33 % (n = 7.689).
- Matchup vs Shu: 56,36 %, n = 692. Vs Wu: 50,60 %, n = 583.

Limitaciones verificadas de esta API en el patch actual:

- `by_opening` y `opening_stats` están **todos en cero** (`ci_lower: -1.0` como centinela), por
  falta de datos de replay. Las aperturas hay que sacarlas de AoE Pulse.
- `avg_feudal_time`, `avg_castle_time`, `avg_imperial_time` valen **0** por lo mismo.
- `map_stats[x].by_civ` viene vacío; la vista civ→mapa sí existe (`civ_stats[c].by_map`).
- Sólo 50 civs: **faltan Mapuche, Muisca y Tupi** (y el rework de Incas no está reflejado).
- De esas 50, **Khitans y Jurchens figuran con 0 partidas** en el patch 162286 (verificado en el
  payload al cargarlo). O sea que en la práctica hay **48 civs con estadística de 53 jugables**.

---

## 2. AoE Pulse — aperturas y timings

Sitio: <https://www.aoepulse.com/> · Motor de detección de aperturas (open source):
<https://github.com/dj0wns/AoE_Openings> sobre <https://github.com/happyleavesaoc/aoc-mgz>.

Es una SPA React con API REST propia, no documentada pero funcional. Endpoints hallados en el
bundle `main.81a3227d.chunk.js`:

```
/api/v1/info/               catálogos (41 patches, 50 civs, 2 ladders, 56 mapas, 15 aperturas)
/api/v1/civ_win_rates/      win rate por civ
/api/v1/opening_win_rates/  win rate por apertura
/api/v1/opening_matchups/   apertura A vs apertura B
/api/v1/meta_snapshot/      play rate de cada apertura por tramo de Elo (de 50 en 50)
/api/v1/advanced/           (devuelve vacío)
```

**Parámetros reales** (los nombres obvios como `map_ids` se ignoran silenciosamente):
`include_patch_ids`, `include_ladder_ids`, `include_map_ids`, `include_civ_ids`,
`exclude_civ_ids`, `clamp_civ_ids`, `include_opening_ids`, `min_elo`, `max_elo`.

Las 15 aperturas clasificadas: Premill Drush Any/FC/Range Followup, Postmill Drush ídem,
MAA Any / No Feudal Followup / Range Followup, Scouts Any / No Feudal Followup / Range Followup,
Range Opener Any, Straight FC, Unknown. Ladders: Random Map 1v1 (id 3), Empire Wars 1v1 (id 13).

**Prueba de fuego, consulta real** (patch 162286, RM 1v1, Elo 1000-1200):

| Mapa | Apertura | n | win rate |
|---|---|---|---|
| Arabia (id 9) | Scouts Any | 103.672 | **54,3 %** |
| Arabia | Scouts No Feudal Followup | 105.594 | 53,0 % |
| Arabia | Range Opener Any | 67.000 | **46,8 %** |
| Arena (id 29) | Straight FC | 64.968 | **56,3 %** |

Los números son coherentes con el consenso del juego (en Arabia el scout rush rinde; en Arena el
Fast Castle domina), lo cual valida que los filtros efectivamente se aplican.

⚠️ **Caveats pendientes de aclarar antes de usarlo en producción**: las categorías se solapan
("Scouts Any" incluye sus follow-ups), y la suma de `total` por apertura no coincide con el
`total` global de la respuesta. Hay que definir con precisión la unidad de conteo
(¿partida o jugador-partida?) antes de mostrar porcentajes. Última fecha con datos: patch 162286,
igual que aoestats.

---

## 3. Datos exactos del juego

### 3.1 aoe2techtree (MIT) — costos, HP, ataque, tiempos

<https://github.com/SiegeEngineers/aoe2techtree> · archivo
`data/data.json` (0,88 MB, actualizado 21-jun-2026).

Contiene `civs` (**53 civs**, ya incluye Mapuche/Muisca/Tupi/Shu/Wei/Wu/Jurchens/Khitans),
`data.Unit` (245), `data.Tech` (194), `data.Building` (40), `unit_upgrades` y `age_names`.

Ejemplo de unidad (Archer, id 4): `Cost {Wood: 25, Gold: 45}`, `HP 30`, `Attack 4`, `Range 4`,
`ReloadTime 2`, `AttackDelaySeconds 0.35`, `Speed 0.96`, `TrainTime 35`, `MeleeArmor 0`,
`PierceArmor 0`, más los vectores `Attacks`/`Armours` por clase de armadura.
Ejemplo de tech: `{"Cost": {"Food": 750, "Gold": 450}, "ResearchTime": 70, "internal_name": "Mayan El Dorado"}`.

**Lo que NO trae**: el efecto numérico de los bonos de civilización. `civs.<Civ>.meta` está vacío
(`{}`) y el bono sólo existe como **texto** en `data/locales/<lang>/strings.json`. Hay español,
verificado — Francos (`help_string_id: 120151`):

> Civilización de caballería · Los recolectores trabajan un 15 % más rápido · Tecnologías de
> molino gratuitas · Las unidades montadas obtienen un 20 % más de PR a partir de la Edad Feudal ·
> Los castillos cuestan un 15/25 % menos…

→ **Consecuencia de diseño**: los bonos hay que modelarlos a mano, en un YAML propio, citando
como fuente el texto oficial del juego. Es trabajo manual acotado (53 civs) y es la única forma
de calcular "cuántos recursos netos vale el bono de X al minuto Y".

### 3.2 aoe2dat — las tasas de recolección, extraídas del .dat

<https://github.com/hszemi/aoe2dat> · `data/full.json.xz` (7,3 MB comprimido, actualizado
18-feb-2026). ⚠️ **Sin licencia declarada** — usar como referencia, no redistribuir.

Es el volcado directo del `.dat` del juego. Las tasas de trabajo están en
`Civs[i].Units[j].Bird.WorkRate`. Verificado (civ British, valores base):

| Unidad interna | Tarea | WorkRate (rec./s) |
|---|---|---|
| VMFOR | bayas | **0,31** |
| VMSHE | ovejas | **0,33** |
| VMHUN | caza / jabalí | **0,41** |
| VMLUM | madera | **0,39** |
| VMMIN | oro y piedra | **0,36** |
| VMFAR | granja | **0,53** (bruto; el efectivo con caminata ronda 0,32) |

Además: `Speed` del aldeano = 0,8; capacidad de carga en `ResourceStorages`; `Bird.TaskList` con
las 20 tareas del aldeano base; `Creatable.TrainTime` y `ResourceCosts`.

Los valores coinciden con los publicados en la wiki de la comunidad, lo que da doble
confirmación. Nota importante para el motor: **el WorkRate no es la tasa efectiva** — hay que
descontar caminata al depósito y capacidad de carga. Ahí es donde un simulador serio se
complica (ver `design.md`, sección de alcance).

---

## 4. Build orders documentados

### 4.1 rtsbuilds / RTS Overlay (GPL-3.0) — 41 builds en JSON, con autor y fuente

Repo de datos: <https://github.com/CraftySalamander/rtsbuilds> →
`docs/api/builds/aoe2/*.json` (42 archivos, actualizado 16-jun-2026).
Overlay: <https://github.com/CraftySalamander/RTS_Overlay> (109 ★).
Editor web: <https://rts-overlay.github.io/> · Catálogo: <https://buildorderguide.com>

Los builds están parametrizados por civ (`"civilization": "Generic"` o una civ concreta) y hay
específicos por escenario: `arenafastcastleboom`, `khm19popknightssuperrush`,
`geo19popfastknights`, `bur flemishmilitiarush`, etc.

**Formato verificado** (extracto de `scoutsrush18pop.json`):

```json
{
  "name": "Scouts rush - 18 pop",
  "civilization": "Generic",
  "author": "Morley Games",
  "source": "https://youtu.be/PcKxbQKlZH8",
  "build_order": [
    { "villager_count": 9, "age": 1,
      "resources": { "wood": 2, "food": 7, "gold": 0, "stone": 0 },
      "notes": ["Next 2 @resource/MaleVillDE.webp@ to wood (build lumber camp) | Start pushing deer"],
      "time": "2:30" }
  ]
}
```

Es exactamente el modelo que necesitamos: paso a paso, con reparto de aldeanos por recurso,
edad, timing objetivo y notas. **Decisión propuesta: adoptar este esquema tal cual** (extendido
con campos propios) y no inventar uno nuevo. Los `@…webp@` son marcadores de íconos: se parsean
y se reemplazan por texto o por el ícono correspondiente.

### 4.2 Hera y otros pros — restricción de licencia

La guía de Hera (24 build orders con análisis, actualizada a 2025) circula como **PDF de pago
vía Patreon** (<https://www.patreon.com/posts/build-orders-87609850>) y en sitios que la
rehospedan (ageofnotes.com, maggew.com). **No es redistribuible.** Lo mismo aplica a material
exclusivo de suscriptores de Twitch.

→ Regla del proyecto: la app **no incluye** builds de pago. Usa los de fuente abierta con
atribución (`author` + `source` visibles en pantalla), y si Iván tiene el PDF de Hera comprado,
puede cargarlo en su instalación local — pero no se versiona en el repo.

Referencia metodológica (no de datos): **Spirit of the Law** en YouTube, para el estilo de
análisis cuantitativo (amortizaciones, costo-efectividad, valor de bonos en recursos).

---

## 5. Prior art — qué ya existe

| Herramienta | Qué hace | Qué le falta |
|---|---|---|
| **aoecoach.com** ⚠️ | **Mismo nombre y misma promesa**: "AI advisor" con análisis de matchup, plan de juego, counters, coaching en vivo por audio. Freemium. | Es una caja negra: no muestra n, ni IC, ni de qué patch salen los números. Imposible auditar si el consejo sale de datos o del modelo. |
| aoestats.io | Las mejores estadísticas por civ | No recomienda nada; no habla de build orders |
| aoepulse.com | Aperturas y su win rate | Igual: sólo describe, no aconseja; UI cruda |
| buildorderguide.com / RTS Overlay | Builds paso a paso + overlay in-game | No sabe nada de estadísticas ni de tu matchup: vos elegís el build a ciegas |
| aoe2insights, aoe2.gg, aoecompanion | Perfiles y ladder | aoecompanion tiene stats de **2021**; insights bloquea scraping (403) |
| aoe2techtree.net | Árbol tecnológico | Datos crudos, sin interpretación económica |
| [aoe2-bo-simulator](https://github.com/TMB-2197/aoe2-bo-simulator) | Simula gather rates, carga y caminata para validar builds | Proyecto chico (1 ★, sin tocar desde 2023), sin licencia |

**El hueco real**: nadie une las tres capas — *qué dicen los datos* (estadística con n e IC),
*qué hacen los pros* (build orders documentados) y *por qué conviene* (aritmética del juego con
valores exactos del .dat). Y nadie es honesto sobre la antigüedad de sus datos.

**Nuestro diferencial, entonces**:
1. **Trazabilidad total**: cada número con fuente, n y fecha del dato. Si n < 200, se dice.
2. **Honestidad de patch**: cartel visible de "datos del patch 162286; vos jugás el 177723" y
   marca explícita en las civs sin datos (Mapuche, Muisca, Tupi, Incas reworkeadas).
3. **Separación de capas**: la estadística *elige* la estrategia; el build order viene de una
   fuente pro *citada*; la aritmética *justifica*. Nada se inventa.
4. Local, gratis, sin cuenta, y con los datos en disco para poder auditarlos.

---

## 6. Otras fuentes evaluadas y descartadas (o de reserva)

- **Kaggle "Age of Empires II DE Match Data"** (jerkeeler = autor de aoestats): es el mismo dump,
  con el mismo corte. No agrega nada; sirve sólo como espejo si aoestats se cae.
- **LibreMatch / relic community endpoints** (<https://wiki.librematch.org/>): la fuente primaria
  de la que come aoestats. Es el **plan B estructural**: si queremos datos posteriores a
  feb-2026, hay que recolectarlos nosotros. Trabajo real (polling, parseo, almacenamiento).
- **aoe2.net**: discontinuada. Confirmado que ya no es alternativa.
- **aoe2meta.com**: no resolvió DNS al momento de la prueba (17-ago-2026).
- **Fandom / Liquipedia**: buenas para texto y para chequear un valor suelto; Fandom devolvió
  402 al scraping automatizado. No sirven como fuente estructurada.

### Para la Fase 4 (post-partida)

- **aoc-mgz** (MIT, 233 ★, activo a mar-2026): parser de `.aoe2record` en Python, con
  *summary* de alto nivel. Es la opción por defecto.
- **aoe2rec** (Rust/WASM/Python) y **genie-rs** como alternativas.
- **AoE_Openings** (dj0wns): clasificador de aperturas sobre mgz, es el que usa AoE Pulse.
  Sin licencia declarada y sin commits desde 2022 — mirar la lógica, no depender del código.

---

## 7. Estado del entorno (verificado en esta PC)

- Python 3.12.10 en `C:\Users\ivann\AppData\Local\Programs\Python\Python312`.
- Sin `duckdb`, `pandas` ni `pyarrow` instalados a nivel global → el proyecto usa venv propio.
- `duckdb` 1.5.5 instalado y probado en un venv temporal: lee los Parquet de aoestats
  directamente por URL o por archivo, sin conversión previa.
- Acceso a red OK desde PowerShell y desde `curl`.
