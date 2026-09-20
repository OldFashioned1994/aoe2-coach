# AoE2 Coach — Diseño y arquitectura (Fase 0)

Documento de decisiones. Todo lo que acá se afirma sobre fuentes está verificado en
[`research.md`](research.md).

---

## 1. Qué construimos, en una frase

Una app local que, dado `{mi civ, mapa, mi Elo, civ rival}`, devuelve **una estrategia
recomendada con su respaldo estadístico (n + IC + patch), el build order pro que la ejecuta
(citado a su autor), la aritmética de las 2-3 decisiones clave, y un plan B con señales de
scouting** — sin inventar un solo número.

## 2. Los tres pilares, y qué hace cada uno

La regla que ordena todo el diseño: **cada capa hace una sola cosa y no invade a la otra.**

| Capa | Fuente | Responsabilidad | Qué NO hace |
|---|---|---|---|
| **Estadística** | aoestats `/api/stats/` + AoE Pulse | *Elegir* qué estrategia conviene y con cuánta confianza | No genera build orders |
| **Build orders** | rtsbuilds (GPL-3.0), con autor y URL | *Ejecutar* la estrategia paso a paso | No se "optimiza" ni se recalcula |
| **Aritmética** | `data.json` (MIT) + work rates del `.dat` | *Justificar* con números exactos del juego | No decide la estrategia |

Si una recomendación no puede apoyarse en las tres, la app lo dice en vez de rellenar.

## 3. Stack — decisión y por qué

| Componente | Elección | Justificación |
|---|---|---|
| Lenguaje | **Python 3.12** + venv del proyecto | Ya instalado; es donde vive el ecosistema (mgz para Fase 4) |
| Datos | **DuckDB** (archivo `aoe2coach.duckdb`) | Lee Parquet nativamente, hace las agregaciones en SQL, cero servidor, un solo archivo respaldable |
| Backend | **FastAPI** | Tipado con Pydantic → el contrato de salida del motor queda documentado solo (`/docs`) |
| Vistas | **Jinja2 + CSS propio** (sin HTMX, ver decisión 13) | Cero build step, cero `node_modules`. El formulario y las tablas son HTML que rinde el servidor; la checklist lleva 35 líneas de JS propio |
| Gráficos | SVG generado en Python | Los dos o tres gráficos (win rate vs duración, uptime) no justifican una librería JS |
| Tests | pytest | Incluye tests de calidad de datos (Fase 1) |

**Descartado**: React/Next (build step innecesario para un formulario y una lista);
Streamlit (rápido de arrancar, pero la vista checklist "grande, para seguir mientras juego"
pelea con su layout); Postgres (nada acá necesita concurrencia ni servidor).

**Interfaz**: una web local en `localhost:8000`. Frente a una CLI, gana porque la vista
checklist en segunda pantalla mientras jugás es el modo de uso real, y ahí un terminal
no sirve.

## 4. Arquitectura de carpetas

```
27-aoe2-coach/
├─ docs/                  research.md, design.md, decisiones.md
├─ data/
│  ├─ raw/                descargas crudas (parquet, json) — no se versiona
│  ├─ ref/                datos de referencia versionados (YAML/JSON escritos por nosotros)
│  │  ├─ civ_bonuses.yaml     ← el trabajo manual: bonos con su efecto numérico y su cita
│  │  ├─ strategies.yaml      ← catálogo de estrategias: el puente entre los 3 vocabularios
│  │  ├─ unidades_alias.yaml  ← nombres legibles → nombre interno del .dat
│  │  ├─ pesos.yaml           ← los pesos del scoring, editables sin tocar código
│  │  ├─ iconos_alias.yaml    ← íconos de los builds → palabra en español
│  │  ├─ gather_rates.json    ← destilado del .dat (generado)
│  │  └─ tech_effects_eco.json ← destilado del .dat (generado)
│  ├─ builds/             build orders JSON (bajados de rtsbuilds, con autor y source)
│  └─ aoe2coach.duckdb    la base
├─ src/aoe2coach/
│  ├─ ingest/             descarga y carga: aoestats_api.py, aoepulse_api.py,
│  │                      dumps.py, techtree.py, datfile.py
│  ├─ transform/          limpieza, normalización, agregados (SQL en .sql versionado)
│  ├─ engine/             el motor: modelos, evidencia, aritmetica, motor, presentacion
│  ├─ api/                FastAPI: app.py con las 4 rutas
│  └─ web/                templates/ (Jinja) + static/ (estilo.css, checklist.js)
└─ tests/
```

## 5. Modelo de datos

Tres capas dentro de DuckDB, con la convención `raw_ / ref_ / mart_`:

**raw_** — copia fiel de la fuente, sin tocar. En la implementación quedó así: los JSON de las
APIs viven como **archivos** en `data/raw/` con su sidecar `.meta.json` (URL, fecha, MD5) y la
trazabilidad la da la tabla `ingest_log` — meterlos también en la base no aportaba nada y los
hacía menos inspeccionables. Sí son tablas los Parquet: `raw_matches` y `raw_players`, con las
vistas limpias `clean_matches_1v1` y `clean_players_1v1`.

**ref_** — datos del juego y catálogos: `ref_unit`, `ref_tech`, `ref_building`, `ref_civ`,
`ref_gather_rate`, `ref_tech_effect` (qué tech multiplica qué tasa, extraído del .dat),
`ref_build_order` + `ref_build_step`. Los catálogos escritos a mano (bonos, estrategias, pesos,
alias) quedaron como YAML en `data/ref/` en vez de tablas: se editan y se revisan mejor, y un
test los valida contra el juego.

**El perfil de los mapas no se declara: se deriva** (`mart_map_profile`). Ver §5.1.

**mart_** — lo que consulta el motor, ya con estadística resuelta:

```
mart_civ_performance   (patch, elo_bucket, map, civ,
                        n, wins, win_rate, ci_low, ci_high, play_rate, source, fetched_at)
mart_matchup           (patch, elo_bucket, map, civ, opp_civ, n, win_rate, ci_low, ci_high, …)
mart_opening           (patch, elo_bucket, map, opening, n, win_rate, ci_low, ci_high, …)
mart_opening_matchup   (patch, elo_bucket, map, opening, opp_opening, n, win_rate, …)
mart_civ_by_duration   (patch, elo_bucket, civ, bucket {quick|medium|med_long|long}, n, win_rate)
mart_map_play_rate     (patch, elo_bucket, map, n, play_rate)
mart_patch             (patch, label, release_date, url, descripcion, total_games)
mart_uptime_historico  (patch, elo_bucket, map, opening, n, feudal_p25/p50/p75, castle_p50, …)
```

`mart_uptime_historico` sale de los dumps de 2023 (los únicos con datos de replay) y **no se
mezcla** con lo demás: sirve para saber cómo ejecuta la gente, no para decidir qué civ conviene
hoy.

**Reglas no negociables del esquema**:
- Ninguna tabla `mart_` existe sin columnas `n`, `ci_low`, `ci_high`, `patch`, `source`.
  Si no se puede calcular el IC, la fila no entra.
- IC por **Wilson score** al 95 % calculado por nosotros, aunque aoestats ya lo traiga:
  así el criterio es uniforme entre fuentes y auditable. Los valores centinela de aoestats
  (`ci_lower: -1.0`) se descartan en la carga.
- `elo_bucket` se normaliza a los 5 tramos de aoestats (`low`, `med_low`, `medium`,
  `med_high`, `high`) + `all`; el Elo que ingresa el usuario se mapea a su tramo y la app
  muestra a qué tramo cayó.

### 5.1 Perfil de mapa derivado de datos

En vez de un YAML donde alguien escribe "Arena es cerrado", se miden dos indicadores:

- **fc_share**: proporción de Straight FC entre las aperturas del mapa. Arena da 59 %, Arabia
  9 %. Corte: ≥40 % cerrado, ≥18 % semicerrado, el resto abierto.
- **naval_share**: proporción de aperturas navales en el corpus de 2023. Islands 65 %, Baltic
  49 %, Arabia 0 %. Sirve para marcar los mapas que el overhaul naval dejó sin datos válidos.

Los umbrales son juicio nuestro y están en `transform/map_profile.py`, arriba de todo. Los mapas
sin muestra quedan como `desconocido` y el motor lo dice.

### Limpieza (Fase 1) — checklist derivado de lo verificado

1. Descartar `num_players` impar (basura confirmada: 1 partida con 7 jugadores en una semana).
2. 1v1 RM = `leaderboard = 'random_map' AND num_players = 2`.
3. Castear `opening` a VARCHAR siempre (cambia de tipo entre dumps: ver research §1.3).
4. Descartar duración fuera de [5 min, 180 min] — aoestats ya lo hace, lo re-verificamos.
5. Normalizar nombres de mapa y civ contra `ref_map` / `ref_civ`; **fallar ruidosamente** ante
   un nombre desconocido en vez de descartarlo en silencio (así detectamos civs nuevas).
6. Registrar en `ingest_log` cada descarga: URL, checksum MD5 del dump, filas, fecha.

## 6. El motor de recomendación

### 6.1 Entrada / salida

```python
class Contexto(BaseModel):
    civ: str | None          # None = "recomendame civ"
    mapa: str
    elo: int
    civ_rival: str | None
    modo: Literal["rm_1v1"] = "rm_1v1"
```

La salida es un `Reporte` tipado con cinco bloques, y **cada número dentro lleva su
`Evidencia`**:

```python
class Evidencia(BaseModel):
    valor: float
    n: int | None
    ci: tuple[float, float] | None
    fuente: str              # "aoestats /api/stats/ patch 162286"
    fecha_dato: date
    confianza: Literal["alta", "media", "baja", "sin_datos"]
```

`confianza` se deriva de reglas fijas, no del criterio del momento:
`alta` n ≥ 2.000 y patch vigente · `media` n ≥ 200 · `baja` n < 200 · `sin_datos` n = 0.
Como hoy **ningún** dato es del patch vigente, el techo real de confianza es `media` mientras
no haya recolección propia. La app lo dice de entrada.

### 6.2 Cómo elige la estrategia

No es un modelo entrenado ni un LLM: es un **scoring explícito y auditable**, y en pantalla se
muestra cómo se compuso el puntaje.

Los términos estadísticos usan el **límite inferior del intervalo de Wilson**, no el promedio:
así una muestra chica se descuenta sola (ver `decisiones.md`).

```
score(estrategia) = w1 · piso_intervalo_apertura(mapa, elo)   [AoE Pulse]
                  + w2 · afinidad_civ(estrategia, civ)         [ref_civ_bonus, calculada]
                  + w3 · ventaja_matchup(civ, civ_rival, mapa) [aoestats by_matchup]
                  + w4 · contra_apertura_esperada(civ_rival)   [Pulse opening_matchups]
                  − w5 · penalización_por_muestra_chica
                  − w6 · penalización_por_dificultad(elo)
```

- Cada término se muestra desglosado con su n. Sin caja negra.
- **Penalización por dificultad**: un Fast Castle + Caballeros pide precisión de ejecución; a
  1000 de Elo su win rate poblacional no es tu win rate esperado. El catálogo
  `ref_strategy` marca `dificultad: 1-5` y a Elo bajo se penalizan las de 4-5.
  Este es el único parámetro **de juicio, no de dato** en todo el motor → va documentado
  como tal en `decisiones.md` y es ajustable desde el YAML.
- Los pesos `w1..w6` viven en un YAML, no en el código.
- Si `civ_rival` es `None`, el término de matchup se omite y se usa la distribución de
  aperturas del mapa como rival esperado.

### 6.3 Cómo elige el build order

Búsqueda en `ref_build_order`, en este orden de preferencia:
1. Build de la estrategia elegida **específico para mi civ** (ej. `khm19popknightssuperrush`).
2. Build genérico de esa estrategia (`civilization: "Generic"`) **+ ajustes por civ**.
3. Si no hay ninguno: se dice que no hay build documentado y se ofrece el más cercano,
   marcado como tal.

Los **ajustes por civ** salen de `ref_civ_bonus` y son reglas explícitas y citadas
(ej.: "los Francos tienen las techs de molino gratis → el paso *investigar Doble Filo* no
aplica igual"). Cada ajuste muestra el texto del bono como fuente. **Ningún paso del build se
inventa ni se reordena por cuenta propia**: sólo se anotan, agregan o tachan pasos según una
regla escrita.

### 6.4 El módulo de aritmética — alcance honesto

Acá está el riesgo de sobre-prometer, así que el alcance queda acotado desde ahora:

**Sí hacemos** (cálculo cerrado, resultado exacto y verificable):
- **Amortización de una tech**: Doble Filo cuesta 100 madera / 50 s. Con `WorkRate` de madera
  0,39 rec/s y +20 % de la tech, N leñadores recuperan el costo en `t = 100 / (N · 0,39 · 0,20)`
  segundos. Se muestra la fórmula con sus valores.
- **Valor del bono de civ en recursos/minuto**: bono de Francos (recolectores +15 %) con
  X aldeanos en cada recurso → recursos extra/minuto al minuto M.
- **Costo-efectividad de unidad A vs B**: DPS/costo y EHP/costo contra una composición rival,
  usando `Attack`/`Armours` por clase de armadura de `data.json` (incluye el bono de ataque
  por clase, que es donde se define un counter de verdad).
- **Uptime teórico** de un build order: sumar los `time` declarados y contrastarlos con el
  ideal aritmético.

**No hacemos (todavía)**: simulador económico completo tick a tick. Requiere modelar caminata,
capacidad de carga, tiempo de construcción, pathing y decaimiento del jabalí. Es un proyecto en
sí mismo y sería el punto más probable de dar números lindos y falsos. Los timings salen de los
builds documentados y del corpus histórico de replays (2023), no de una simulación propia.
Si más adelante lo queremos, la referencia es
[aoe2-bo-simulator](https://github.com/TMB-2197/aoe2-bo-simulator).

### 6.5 Plan B y scouting

`ref_strategy` incluye, por estrategia, una lista de `señales` con la forma
*"si ves X antes del minuto Y → transicioná a Z"*. Su respaldo es doble: el counter sale de la
aritmética (§6.4) y la frecuencia con que aparece ese X sale de `mart_opening` del mapa. Las
señales que no tengan ninguno de los dos respaldos no se cargan.

## 7. Frescura de los datos: cómo lo maneja la app

Es *el* problema del proyecto (research §0). El diseño lo trata de frente:

1. Banner permanente: **"Datos: patch 162286 (2-dic-2025), 1.027.074 partidas 1v1 RM.
   Patch vigente del juego: 177723 (2-jun-2026)."**
2. Las civs sin datos (**Mapuche, Muisca, Tupi**, más los Incas reworkeados) se marcan
   `sin_datos` y la app las responde con aritmética y tech tree, diciendo explícitamente que
   no hay estadística.
3. El **overhaul naval del 169123** invalida cualquier recomendación en mapas de agua con datos
   viejos → los mapas marcados `agua: true` en `map_profiles.yaml` bajan a confianza `baja`.
4. Cada ejecución del pipeline chequea si aoestats volvió a publicar dumps; si vuelve, se avisa.
5. **Reserva** (no en el alcance inicial): recolector propio contra los relic community
   endpoints vía LibreMatch. Es la única salida real si el corte se vuelve permanente.

## 8. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Los datos nunca se actualizan | Alto — la app envejece sola | Todo etiquetado por patch; la aritmética y los builds siguen valiendo; recolector propio como reserva |
| APIs no documentadas (aoestats `/api/stats/`, Pulse `/api/v1/`) cambian o se cortan | Alto | Cachear en disco todo lo descargado, con fecha. La app funciona offline con el último snapshot |
| Semántica confusa del `total` de AoE Pulse (research §2) | Medio | Resolverlo antes de mostrar porcentajes; si no se resuelve, mostrar sólo win rate y n, nunca play rate |
| Modelado manual de 53 civs (bonos) | Medio — es trabajo y puede tener errores | Empezar por las 12-15 civs más jugadas; cada bono con test unitario contra el texto oficial |
| Licencias | Medio | rtsbuilds es GPL-3.0 (atribución + copyleft si distribuimos); aoe2dat **sin licencia** (referencia, no redistribución); nada de Hera/Patreon en el repo |
| El scoring "parece" objetivo pero tiene pesos elegidos a mano | Medio | Pesos en YAML, desglose visible en pantalla, `dificultad` documentada como juicio |
| Nombre colisiona con aoecoach.com | Bajo | Ver §10 |

## 9. Plan de fases

| Fase | Entregable | Criterio de terminada |
|---|---|---|
| **1** Pipeline ✅ | Ingesta + limpieza + marts + tests | Hecho: reproduce Francos en Arabia (51,40 %, n=51.920) con diferencia < 0,1 pp |
| **2** Motor ✅ | `Reporte` completo para un contexto | Hecho: 40 tests en verde, cada número rastreable a su fuente |
| **3** Interfaz ✅ | Formulario → reporte; checklist; explorador | Hecho: FastAPI + Jinja, sin build step ni JavaScript de terceros |
| **4** Post-partida | Sólo diseño escrito, sin código | Documento de cómo comparar replay vs build objetivo |

Sugerencia de arranque para la Fase 1: **empezar por la API de agregados**, no por los Parquet.
Con `/api/stats/` (6,7 MB) ya se cubre el 80 % de lo que el motor necesita, y los dumps quedan
para el corpus histórico de uptimes. Menos código y resultado visible antes.

## 10. Decisiones que necesito de vos antes de la Fase 1

1. **El nombre.** `aoecoach.com` ya existe con el mismo nombre y casi la misma promesa
   (research §5). Como es de uso personal no hay problema legal, pero si en algún momento lo
   publicás conviene otro. ¿Lo dejamos como AoE2 Coach o le buscamos nombre?
2. **Tu Elo y tus mapas.** Si me decís tu rango real (¿1000-1200?) y si jugás Arabia, Arena o
   ambos, priorizo el modelado de bonos y el catálogo de builds por ahí en vez de cubrir las
   53 civs parejo.
3. **El corte de datos.** Confirmame que aceptás arrancar con datos del patch 162286 (pre-DLC),
   con los carteles de advertencia. La alternativa es meter primero el recolector propio contra
   los relic endpoints — bastante más trabajo antes de ver algo funcionando.
4. **Alcance de la aritmética.** ¿Te sirve el alcance acotado de §6.4 (amortizaciones, valor de
   bonos, costo-efectividad) o querés el simulador económico completo? Recomiendo lo acotado:
   el simulador es donde más fácil se producen números lindos y falsos.
5. **Stack de UI.** Propongo FastAPI + Jinja + HTMX (§3). Si preferís otra cosa, es el momento.
