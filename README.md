# AoE2 Coach

App local de estrategia y build orders para **Age of Empires II: Definitive Edition**.
Dado tu contexto de partida (civ, mapa, Elo, civ rival) recomienda una estrategia y su build
order paso a paso, con la justificación estadística y matemática detrás — cada número con su
fuente y su tamaño de muestra.

> **Estado**: Fases 1, 2 y 3 terminadas — pipeline de datos, motor de recomendación y web
> local. Queda la Fase 4 (análisis post-partida), que por ahora es sólo diseño.

## Advertencia de datos, de entrada

Las estadísticas disponibles son del **patch 162286 (2-dic-2025)**; el juego corre el
**177723 (2-jun-2026)**. Todo el ecosistema de estadísticas de AoE2 dejó de ingerir partidas el
**7-feb-2026**, diez días antes del DLC *The Last Chieftains* y del rework naval. La app lo
declara en pantalla y marca las civs sin datos (Mapuche, Muisca, Tupi) en vez de disimularlo.
El detalle está en [docs/research.md](docs/research.md).

## Usarlo ya (Windows)

1. **`instalar.bat`** — una sola vez: arma el entorno y descarga los datos (~15 MB, un par de
   minutos).
2. **`iniciar.bat`** — cada vez: levanta la app y abre el navegador en
   <http://127.0.0.1:8000>. Si falta algo, lo instala solo.

Para cerrarlo, cerrá la ventana negra.

## Instalación a mano

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli ingest
```

## Uso

```bash
# la web local: formulario, reporte, checklist para jugar y explorador de datos
PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli web
# → http://127.0.0.1:8000

# lo mismo por consola

PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli recomendar \n    --civ franks --mapa arabia --elo 1100 --rival mayans

# descarga y carga todas las fuentes (la primera vez tarda: baja ~15 MB)
PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli ingest

# sólo una fuente: aoestats | pulse | techtree | dat | builds | dumps
PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli ingest --solo pulse

# ficha de una civilización: bonos, fortalezas medidas y qué le falta
PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli civ turks --elo 500

# estado de la base y última ingesta por fuente
PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli info

# controles de calidad de datos
PYTHONPATH=src .venv/Scripts/python.exe -m aoe2coach.cli check

# tests
.venv/Scripts/python.exe -m pytest
```

Todo lo descargado queda cacheado en `data/raw/` con un sidecar `.meta.json` (URL, fecha, MD5),
así que después de la primera corrida la app funciona sin internet.

## Fichas de civilización

Cada civ tiene su página (`/civ/turks`) con tres capas bien separadas:

1. **Bonos**: el texto del juego, tal cual, con unidad única, tecnologías únicas y bono de equipo.
2. **Fortalezas medidas**: si rinde en partidas cortas o largas, sus mejores y peores mapas y
   contra qué civs gana o sufre — todo con su n y su intervalo.
3. **Qué le falta**: comparación literal contra el árbol oficial de la civ. Los Turcos no tienen
   Alabardero, los Francos no tienen Linaje, los Britones no tienen pólvora.

## Cómo decide

Tres capas separadas, y ninguna invade a la otra:

1. **La estadística elige.** Un puntaje explícito suma win rate de la apertura en ese mapa y
   tramo de Elo, afinidad de tu civ, matchup y qué tan bien le va contra lo que probablemente
   juegue el rival; y resta muestra chica, dato fuera de contexto, mapa que no acompaña y
   dificultad de ejecución. El desglose se imprime siempre: el puntaje no es una caja negra.
2. **El build order se cita.** Sale de una fuente pro documentada, con autor y URL, y se anota
   según los bonos de tu civ. No se reordena ni se inventa ningún paso.
3. **La aritmética justifica.** Amortización de tecnologías, valor del bono de tu civ en
   recursos y costo-efectividad contra el counter esperado, con la fórmula y los supuestos a la
   vista. Todo sale del `.dat` del juego.

Los pesos del puntaje viven en `data/ref/pesos.yaml` y se pueden tocar sin abrir el código.

## Fuentes

| Qué | De dónde | Licencia |
|---|---|---|
| Win rate por civ, mapa, matchup y duración | [aoestats.io](https://aoestats.io) `/api/stats/` | Game Content Usage Rules de Microsoft |
| Aperturas y sus matchups | [AoE Pulse](https://www.aoepulse.com) `/api/v1/` | — |
| Costos, HP, ataque, tiempos | [aoe2techtree](https://github.com/SiegeEngineers/aoe2techtree) | MIT |
| Tasas de recolección | [aoe2dat](https://github.com/hszemi/aoe2dat) | sin licencia declarada: referencia, no se redistribuye |
| Build orders | [rtsbuilds](https://github.com/CraftySalamander/rtsbuilds) | GPL-3.0, con autor y fuente citados |

No se incluye material de pago (la guía de Hera es un PDF de Patreon). Si la tenés comprada,
poné los JSON en `data/builds/propios/` — esa carpeta no se versiona.

## Documentación

- [docs/research.md](docs/research.md) — fuentes, esquemas y todo lo verificado contra la API
- [docs/design.md](docs/design.md) — arquitectura, modelo de datos y el motor
- [docs/decisiones.md](docs/decisiones.md) — decisiones tomadas y las que quedan abiertas
