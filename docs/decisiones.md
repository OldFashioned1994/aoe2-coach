# Decisiones

Registro de lo que se decidió, cuándo y por qué. Las que están marcadas **(supuesto)** las tomé
yo para no frenar la Fase 1: si alguna no te cierra, se cambia y se anota acá.

## 2026-08-17 — Fase 0 y arranque de la Fase 1

| # | Decisión | Estado | Razón |
|---|---|---|---|
| 1 | El proyecto se llama **AoE2 Coach** | **(supuesto)** | `aoecoach.com` ya existe con la misma promesa (research §5). Es uso personal, así que no bloquea; si algún día se publica, conviene cambiarlo |
| 2 | Arrancamos con datos del **patch 162286**, con advertencia visible | **(supuesto)** | Es lo único que existe: todo el ecosistema se cortó el 7-feb-2026. La alternativa (recolector propio) es mucho trabajo antes de ver algo andando |
| 3 | Stack **Python + DuckDB + FastAPI + Jinja/HTMX** | **(supuesto)** | Ver design §3. Nada de build step de JS |
| 4 | Aritmética **acotada**: amortizaciones, valor de bonos, costo-efectividad. Sin simulador tick a tick | **(supuesto)** | Es donde más fácil salen números lindos y falsos |
| 5 | Ingesta desde la **API de agregados** de aoestats, no desde los Parquet | firme | 6,7 MB cubren lo que el motor necesita; los dumps quedan para el corpus histórico de uptimes |
| 6 | El **intervalo de Wilson lo calculamos nosotros**, aunque la fuente traiga el suyo | firme | Criterio uniforme entre aoestats y Pulse, y auditable. Se testea contra el de la fuente: máx. 0,5 pp de diferencia |
| 7 | La capa `raw_` son **archivos en disco** con sidecar `.meta.json`, no tablas | firme | Duplicar los JSON dentro de la base no aportaba nada y los hacía menos inspeccionables. La trazabilidad la da `ingest_log` |
| 8 | **No** se versiona material de pago (guía de Hera y similares) | firme | Licencia. Si lo comprás, va en `data/builds/propios/`, que está en el `.gitignore` |
| 9 | El techo de confianza es **"media"** mientras no haya datos del patch vigente | firme | Un n enorme de un patch viejo no vuelve actual a un número viejo |
| 10 | Cobertura de aperturas: mapas con **play rate ≥ 1 %** | firme | 252 requests para cubrirlos todos no se justifica; lo omitido se informa por pantalla, nunca en silencio |

## Hallazgos técnicos de la Fase 1 (van al código, no a la memoria)

- La consola de Windows abre en cp1252 y rompe con `→` y acentos: el CLI fuerza UTF-8 al arrancar.
- `opening` cambia de tipo entre dumps de aoestats (VARCHAR en 2023, INTEGER en 2026 por venir
  todo en NULL).
- La API de AoE Pulse **rechaza con 400 varios rangos de Elo** aparentemente válidos:
  `min_elo=500&max_elo=999` falla, `min_elo=0&max_elo=1000` anda. Los cinco tramos que usamos
  están verificados uno por uno.
- En `opening_matchups` de Pulse, `wins` viene `-1` en los espejos y `null` en combinaciones sin
  partidas: ambos se descartan.
- La **capacidad de carga** del aldeano no se puede leer del volcado de aoe2dat
  (`ResourceStorages` trae flags, no unidades). Queda en `null` hasta tener fuente: preferimos
  el hueco antes que un número falso.
- El repo de builds tiene **41** archivos, no 42 (en el listado del árbol, la primera línea es
  el propio directorio). Corregido en research.md.
- **`duration` de los dumps viene en nanosegundos**, no en segundos como sugiere la doc de
  aoestats (la mediana da 2,68e12 ≈ 44,6 min). Filtrar por `BETWEEN 300 AND 10800` devolvía cero
  filas de 1,25 millones. Se normaliza a `duration_s` en la limpieza.
- **Khitans y Jurchens figuran en aoestats con 0 partidas** en el patch 162286: en la práctica
  hay 48 civs con estadística sobre 53 jugables, no 50. Están en `CIVS_SIN_DATOS_EN_FUENTE`.
- Cinco mapas del ladder actual (glade, graveyards, socotra, shrubland, paradise_island) **no
  existen en el catálogo de AoE Pulse**: quedan sin datos de aperturas y el pipeline lo informa.
  Uno más, `scandanavia`, es un typo de aoestats y se resuelve con alias a `Scandinavia`.
- El intervalo de Wilson con `wins = 0` o `wins = n` cae un ulp fuera de [0,1] en coma flotante
  y dejaba a la proporción afuera de su propio intervalo: se corrige con un clamp explícito.

## Hallazgos técnicos de la Fase 2

- **El oro y la piedra son dos tareas distintas con tasas distintas**: `VMGLD` pica oro a 0,38/s
  y `VMMIN` piedra a 0,36/s. Tratarlas como una sola (como hacía la primera versión) mete un
  error del 5 % en toda cuenta que involucre oro.
- **Los efectos de las tecnologías se pueden sacar del `.dat`**: un `EffectCommand` de tipo 5
  sobre el atributo 13 es "multiplicar la tasa de trabajo". Así, Doble Filo aparece como ×1,2
  exacto, sin depender de ninguna wiki. Se destilaron 121 efectos.
- **Los nombres de las unidades no están en ninguna fuente abierta**: el `strings.json` del tech
  tree trae 1063 cadenas pero no los ids de nombres de unidad, y el `.dat` guarda el id, no el
  texto. De ahí `data/ref/unidades_alias.yaml`, que es traducción nuestra sobre nombres internos
  verificados. Ojo con los nombres heredados de AoE1: el Skirmisher es `XBOWM` y el Camel Rider
  es `CVLRY`.
- El `.dat` y el tech tree escriben distinto los nombres de tech (`Double-Bit Axe` vs
  `Double Bit Axe`): se comparan sin guiones.
- Varias tecnologías no tienen cadena en el locale español; se cae al inglés antes que mostrar
  un nombre vacío.
- **El scoring necesitaba penalizar la evidencia degradada**: sin eso, un win rate de "todos los
  mapas" le ganaba a uno medido en el mapa real. Se agregó el peso `evidencia_degradada` y el
  texto ahora dice de dónde salió cada número en vez de atribuirlo al mapa pedido.
- El perfil de cada mapa (abierto/cerrado, con agua o sin) **se deriva de los datos**, no se
  declara: Arena da 59 % de Fast Castle y Arabia 9 %; Islands da 65 % de aperturas navales en el
  corpus de 2023 y Arabia 0 %.

### El cambio de criterio más importante de la Fase 2

Los componentes estadísticos del puntaje se calculan sobre el **límite inferior del intervalo de
confianza**, no sobre el promedio. El caso que lo motivó: con Britones en Arabia a 1100, el motor
recomendaba Drush → Fast Castle porque marcaba 60,8 % … con n=255 y un intervalo de ±5,9. Contra
eso, Scout rush con 54,3 % y n=63.184 parecía peor. Puntuando por el piso del intervalo (54,7 %
contra 53,9 %) la comparación se vuelve honesta y la muestra chica se castiga sola, sin
penalizaciones inventadas. Es el mismo principio que pediste desde el arranque: "un 56 % con
n=40 no vale nada".

## 2026-09-20 — Fase 3 (web) y decisiones de Nico

| # | Decisión | Estado | Razón |
|---|---|---|---|
| 11 | Elo de referencia: **500**; mapas: Arabia y Arena | firme | Lo definió Nico. Cae en el tramo `low` (0-1000) |
| 12 | El motor **recomienda civ** cuando no la fijás | firme | Pedido de Nico. Elige la mejor y arma el plan con ella |
| 13 | La web va **sin HTMX**, sólo Jinja + un JS propio de 35 líneas | firme | Cambio respecto del diseño: lo único interactivo es la checklist y se resuelve en el cliente. HTMX no aportaba nada |
| 14 | Los íconos de los builds se traducen al español | firme | "MaleVill" y "Aoe2de wood" en medio de la frase eran ilegibles. El texto del autor no se toca: sólo los marcadores de ícono |

### Hallazgos técnicos de la Fase 3

- **El ranking de civs tenía un sesgo del proyecto**: la afinidad con la estrategia sumaba
  puntos, y como sólo 16 de 53 civs tienen los bonos modelados, esas 16 trepaban por lo que yo
  alcancé a cargar y no por rendir mejor. Ahora la afinidad se muestra pero no puntúa; el orden
  lo decide el dato medido. Hay un test que lo vigila.
- **AoE Pulse se cayó** (verificado el 20-sep-2026): `www.aoepulse.com` sirve un certificado de
  `*.pythonanywhere.com` que no es válido para ese dominio, y `aoepulse.com` redirige justo ahí.
  Los datos ya ingeridos siguen en la base y la app funciona igual — para esto se decidió
  cachear todo en disco (decisión 7). No se puede re-ingerir ni ampliar tramos de Elo hasta que
  lo arreglen. **Pendiente de Nico**: esperar, o bajarlo una vez con verificación de certificado
  desactivada (es data pública de sólo lectura).
- **Los mapas "clásicos" no existen en los datos**: Black Forest, Islands, Nomad, Gold Rush,
  Hideout, Four Lakes y Rivers no estaban en la rotación del ladder 1v1 en la ventana capturada.
  Hay civs para 18 mapas y aperturas para 7; de los clásicos sólo Arabia, Arena y Megarandom.
- `TemplateResponse` de Starlette cambió de firma: ahora es `(request, nombre, contexto)`.
  Con la vieja falla con un `TypeError: unhashable type: dict` que no dice nada.
- Edge headless dejó de escribir capturas después de la primera; Playwright (en
  `herramientas/playwright`) sí funciona y además permite simular las teclas de la checklist.

### Fichas de civilización (20-sep-2026)

Pedido de Nico: "faltan bonos y fortalezas de cada civilización, es relevante visualizar eso".
Se agregó `/civ/<civ>` y el comando `cli civ`, con bonos (texto del juego), fortalezas medidas
y carencias del árbol.

**El hallazgo del día**: las listas `civs.<Civ>.Unit` / `.Tech` de `data.json` **no significan
"lo que la civ tiene"**. Incluyen nodos que la civ no tiene habilitados, porque describen qué se
dibuja en el árbol. Con ellas, la primera versión decía que los Godos tienen Arbalestero y que a
los Turcos no les falta nada. El dato correcto es `node_status` de `data/trees/<CIV>.json`:
`NotAvailable` es lo único que significa "no lo tenés". Lo destapó un test que yo mismo había
escrito mal —desde la memoria del juego en vez de desde la fuente—, y al verificarlo resultó que
el equivocado era el test en un caso (los Godos sí tienen Bombarda y Paladín hoy) y la
implementación en el resto.

También: en las tablas de "mejores y peores" mapas, con pocos mapas con muestra el mismo mapa
salía arriba y abajo. Ahora, si hay pocos, se muestra una lista sola.

## Abiertas — necesito tu respuesta

1. **El nombre**: `aoecoach.com` ya existe con la misma promesa. ¿Lo dejamos o lo cambiamos?
   (Los otros tres supuestos —datos del patch viejo, stack y aritmética acotada— quedaron
   confirmados de hecho: el proyecto está construido sobre ellos y funcionan.)
2. **AoE Pulse caído**: ¿esperamos a que arreglen el certificado o lo bajamos una vez sin
   verificarlo?
3. **Los mapas clásicos sin datos**: ¿les pongo un perfil declarado a mano (Black Forest
   cerrado, Islands agua) para que igual respondan con tech tree y aritmética?
