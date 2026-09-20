"""El motor: elige estrategia, trae el build order y arma el reporte.

Cómo decide (docs/design.md §6.2): un puntaje explícito y desglosado, no un modelo. Cada
sumando queda a la vista con su evidencia, así que la recomendación se puede discutir mirando
de dónde salió cada punto.
"""

from __future__ import annotations

from functools import lru_cache

import duckdb
import yaml

from aoe2coach.config import (
    CIVS_SIN_DATOS,
    CIVS_SIN_DATOS_EN_FUENTE,
    DATA_CUTOFF,
    DATA_PATCH,
    DATA_PATCH_DATE,
    GAME_PATCH,
    GAME_PATCH_DATE,
    REF,
    elo_bucket,
)
from aoe2coach.engine import aritmetica
from aoe2coach.engine import evidencia as ev
from aoe2coach.engine.modelos import (
    BuildOrder,
    Calculo,
    CivSugerida,
    Componente,
    Contexto,
    Evidencia,
    EstrategiaPuntuada,
    PasoBuild,
    Reporte,
    Senal,
)


def valor_prudente(e: Evidencia) -> float | None:
    """El límite inferior del intervalo, no el punto estimado.

    Es la diferencia entre "60,8 % con n=255" y "54,3 % con n=63.184": el primero suena mejor
    pero su intervalo llega hasta 54,9 %. Puntuar por el piso del intervalo hace que la
    incertidumbre se pague sola, sin necesidad de castigos ad-hoc, y que una muestra grande
    valga por lo que es.
    """
    if e.valor is None:
        return None
    return e.ci[0] if e.ci else e.valor


def miles(n: int | None) -> str:
    """Separador de miles con punto, sin romper las comas del texto que lo rodea."""
    return f"{n:,}".replace(",", ".") if n is not None else "-"


@lru_cache(maxsize=1)
def cargar_ref() -> tuple[dict, dict, dict]:
    def leer(nombre: str) -> dict:
        return yaml.safe_load((REF / nombre).read_text(encoding="utf-8"))

    return leer("strategies.yaml"), leer("civ_bonuses.yaml"), leer("pesos.yaml")


# --- Advertencias de contexto -------------------------------------------------


def advertencias(con: duckdb.DuckDBPyConnection, ctx: Contexto, perfil: dict) -> list[str]:
    avisos = [
        f"Los datos son del patch {DATA_PATCH} ({DATA_PATCH_DATE}), con partidas hasta el "
        f"{DATA_CUTOFF}. El juego corre el patch {GAME_PATCH} ({GAME_PATCH_DATE}): en el medio "
        f"salió el DLC The Last Chieftains y el rework naval.",
    ]
    for civ, rol in ((ctx.civ, "tu civ"), (ctx.civ_rival, "la civ rival")):
        if not civ:
            continue
        if civ in CIVS_SIN_DATOS:
            avisos.append(
                f"{civ.capitalize()} ({rol}) entró con el DLC del 17-feb-2026: no tiene ninguna "
                f"estadística. Lo que sigue se apoya sólo en el tech tree y en la aritmética."
            )
        elif civ in CIVS_SIN_DATOS_EN_FUENTE:
            avisos.append(
                f"{civ.capitalize()} ({rol}) figura en la fuente con 0 partidas en este patch: "
                f"no hay estadística disponible para esa civ."
            )
    if perfil.get("agua") == "si":
        avisos.append(
            "Es un mapa de agua y el patch 169123 rehizo el combate naval: cualquier dato "
            "previo sobre este mapa quedó desactualizado."
        )
    if perfil.get("perfil") == "desconocido":
        avisos.append(
            f"No hay muestra suficiente para perfilar {ctx.mapa}: se usan los promedios "
            f"generales y la recomendación es más floja."
        )
    return avisos


# --- Scoring ------------------------------------------------------------------


def _afinidad(bonos_civ: list[dict], estrategia_id: str) -> tuple[float, list[str]]:
    """Proporción de bonos de la civ que nombran esta estrategia, con las citas."""
    con_favor = [b for b in bonos_civ if b.get("favorece")]
    if not con_favor:
        return 0.0, []
    citas = [b["texto_en"] for b in con_favor if estrategia_id in b["favorece"]]
    return len(citas) / len(con_favor), citas


def puntuar(
    con: duckdb.DuckDBPyConnection, ctx: Contexto, bucket: str, perfil: dict
) -> list[EstrategiaPuntuada]:
    estrategias, bonos, cfg = cargar_ref()
    pesos, umbrales = cfg["pesos"], cfg["umbrales"]
    bonos_civ = (bonos["civs"].get(ctx.civ) or {}).get("bonos", []) if ctx.civ else []

    # Con qué apertura es más probable cruzarse en este mapa y tramo.
    rivales = ev.aperturas_del_rival(con, ctx.mapa, bucket)
    apertura_rival = next(
        (o for o, _ in rivales if not o.endswith(("Followup",))), rivales[0][0] if rivales else None
    )

    resultado: list[EstrategiaPuntuada] = []
    for e in estrategias["estrategias"]:
        componentes: list[Componente] = []
        avisos: list[str] = []

        # 1. Win rate de la apertura en este mapa y tramo.
        e_ap = Evidencia(**ev.apertura(con, e["apertura_pulse"], ctx.mapa, bucket))
        if e_ap.valor is not None:
            # Si el dato no es del mapa pedido, el encabezado no puede decir que sí lo es.
            donde = "en todos los mapas" if e_ap.nota else f"en {ctx.mapa}"
            piso = valor_prudente(e_ap)
            componentes.append(Componente(
                nombre="win rate de la apertura",
                puntos=(piso - 0.5) * 100 * pesos["apertura"],
                detalle=(
                    f"{e['apertura_pulse']} {donde}: {e_ap.texto()}"
                    f" — se puntúa por el piso del intervalo ({piso * 100:.1f}%)"
                ),
                evidencia=e_ap,
            ))
            if e_ap.n and e_ap.n < umbrales["muestra_minima"]:
                componentes.append(Componente(
                    nombre="muestra chica",
                    puntos=0.0,
                    detalle=(
                        f"sólo {e_ap.n} partidas; ya está descontado al puntuar por el piso "
                        f"del intervalo en vez del promedio"
                    ),
                ))
            if e_ap.nota:
                componentes.append(Componente(
                    nombre="el dato no es de tu contexto",
                    puntos=-pesos["evidencia_degradada"],
                    detalle=f"hubo que salir del corte pedido — {e_ap.nota}",
                ))
        else:
            avisos.append("no hay datos de esta apertura para tu contexto")

        # 2. Afinidad de la civ, citando los bonos que la empujan.
        if ctx.civ:
            afin, citas = _afinidad(bonos_civ, e["id"])
            if afin > 0:
                componentes.append(Componente(
                    nombre="afinidad de tu civ",
                    puntos=afin * pesos["afinidad_civ"],
                    detalle=f"bonos que la favorecen: {'; '.join(citas)}",
                ))
            elif bonos_civ:
                componentes.append(Componente(
                    nombre="afinidad de tu civ",
                    puntos=0.0,
                    detalle="ningún bono de tu civ apunta a esta estrategia",
                ))

        # 3. Matchup de civs (no distingue mapa: la fuente no lo desglosa).
        if ctx.civ and ctx.civ_rival:
            e_mu = Evidencia(**ev.matchup(con, ctx.civ, ctx.civ_rival, bucket))
            if e_mu.valor is not None:
                componentes.append(Componente(
                    nombre="matchup de civs",
                    puntos=(valor_prudente(e_mu) - 0.5) * 100 * pesos["matchup_civ"],
                    detalle=f"{ctx.civ} contra {ctx.civ_rival}: {e_mu.texto()}",
                    evidencia=e_mu,
                ))

        # 4. Cómo le va a esta apertura contra la más probable del rival.
        if apertura_rival == e["apertura_pulse"]:
            componentes.append(Componente(
                nombre="contra la apertura esperada",
                puntos=0.0,
                detalle=(
                    f"lo más probable es cruzarte con {apertura_rival}, o sea un espejo: "
                    f"la fuente no publica win rate de una apertura contra sí misma"
                ),
            ))
        elif apertura_rival:
            e_vs = Evidencia(**ev.apertura_vs_apertura(
                con, e["apertura_pulse"], apertura_rival, ctx.mapa, bucket))
            if e_vs.valor is not None:
                componentes.append(Componente(
                    nombre="contra la apertura esperada",
                    puntos=(valor_prudente(e_vs) - 0.5) * 100 * pesos["contra_apertura_esperada"],
                    detalle=f"contra {apertura_rival}: {e_vs.texto()}",
                    evidencia=e_vs,
                ))

        # 5. ¿El mapa es el terreno de esta estrategia?
        if perfil.get("perfil") not in ("desconocido", None) and \
                perfil["perfil"] not in e["perfiles_mapa"]:
            componentes.append(Componente(
                nombre="el mapa no acompaña",
                puntos=-pesos["perfil_incompatible"],
                detalle=(
                    f"{ctx.mapa} es un mapa {perfil['perfil']} "
                    f"(Fast Castle en el {perfil['fc_share'] * 100:.0f}% de las partidas, "
                    f"n={miles(perfil['n_aperturas'])}) y esta estrategia rinde en "
                    f"{' o '.join(e['perfiles_mapa'])}"
                ),
            ))

        # 6. Dificultad de ejecución: el único término de juicio, no de dato.
        if (e["dificultad"] >= umbrales["dificultad_penalizada_desde"]
                and bucket in umbrales["tramos_penalizados"]):
            exceso = e["dificultad"] - umbrales["dificultad_penalizada_desde"] + 1
            componentes.append(Componente(
                nombre="dificultad de ejecución",
                puntos=-exceso * pesos["dificultad"],
                detalle=(
                    f"dificultad {e['dificultad']}/5: en tu tramo, el win rate poblacional de "
                    f"esta apertura no es el que vas a sacar sin ejecutarla fina"
                ),
            ))

        resultado.append(EstrategiaPuntuada(
            id=e["id"],
            nombre=e["nombre"],
            descripcion=e["descripcion"],
            score=round(sum(c.puntos for c in componentes), 2),
            componentes=componentes,
            apertura_pulse=e["apertura_pulse"],
            dificultad=e["dificultad"],
            advertencias=avisos,
        ))

    return sorted(resultado, key=lambda x: x.score, reverse=True)


# --- Build order --------------------------------------------------------------


def elegir_build(
    con: duckdb.DuckDBPyConnection, estrategia_id: str, civ: str | None, bucket: str, mapa: str
) -> BuildOrder | None:
    estrategias, bonos, _ = cargar_ref()
    e = next(x for x in estrategias["estrategias"] if x["id"] == estrategia_id)
    like = " OR ".join(["lower(nombre) LIKE ?"] * len(e["patrones_build"]))
    patrones = [f"%{p.lower()}%" for p in e["patrones_build"]]

    fila, nota = None, ""
    if civ:
        fila = con.execute(
            f"SELECT build_id, nombre, civ, autor, fuente FROM ref_build_order "
            f"WHERE civ = ? AND ({like}) ORDER BY n_pasos DESC LIMIT 1",
            [civ, *patrones],
        ).fetchone()
        if fila:
            nota = f"build específico de {civ} para esta estrategia"
    if not fila:
        fila = con.execute(
            f"SELECT build_id, nombre, civ, autor, fuente FROM ref_build_order "
            f"WHERE civ = 'generic' AND ({like}) ORDER BY n_pasos DESC LIMIT 1",
            patrones,
        ).fetchone()
        nota = (
            f"no hay build documentado específico de {civ} para esta estrategia: va el genérico"
            if civ else "build genérico"
        )
    if not fila:
        return None

    build_id, nombre, civ_build, autor, fuente = fila
    pasos_raw = con.execute(
        "SELECT paso, villager_count, age, food, wood, gold, stone, time, notas "
        "FROM ref_build_step WHERE build_id = ? ORDER BY paso",
        [build_id],
    ).fetchall()

    ajustes = _ajustes_por_civ(bonos, civ)
    pasos = []
    for p in pasos_raw:
        notas = p[8] or ""
        ajuste = next((texto for clave, texto in ajustes if clave in notas.lower()), None)
        pasos.append(PasoBuild(
            paso=p[0], villager_count=p[1], age=p[2], food=p[3], wood=p[4], gold=p[5],
            stone=p[6], tiempo=p[7], notas=notas, ajuste_civ=ajuste,
        ))

    uptime = Evidencia(**ev.uptime_esperado(con, e["opening_2023"], mapa, bucket))
    return BuildOrder(
        build_id=build_id, nombre=nombre, civ=civ_build, autor=autor or "sin autor",
        fuente=fuente or "", pasos=pasos,
        uptime_esperado=uptime if uptime.valor else None,
        nota_seleccion=nota,
    )


def bonos_de_civ(con: duckdb.DuckDBPyConnection, civ: str | None) -> list[str]:
    """Bonos de la civ para mostrar.

    Si la civ está modelada en el YAML, se usan sus citas (que además alimentan los cálculos).
    Si no —son 37 de 53—, se cae al texto oficial del juego: se muestran igual, aunque no
    entren en ninguna cuenta.
    """
    if not civ:
        return []
    _, bonos, _ = cargar_ref()
    modelada = (bonos["civs"].get(civ) or {}).get("bonos", [])
    if modelada:
        return [b["texto_en"] for b in modelada]

    fila = con.execute("SELECT bonos_texto_en FROM ref_civ WHERE civ = ?", [civ]).fetchone()
    if not fila or not fila[0]:
        return []
    lineas = fila[0].split("Unique Unit")[0].split("\n")
    return [
        linea.strip().lstrip("• ").strip()
        for linea in lineas
        if linea.strip() and not linea.strip().endswith("civilization")
    ]


def _ajustes_por_civ(bonos: dict, civ: str | None) -> list[tuple[str, str]]:
    """Anotaciones al build derivadas de los bonos, cada una con la cita que la respalda.

    Sólo se generan para bonos que se pueden aplicar sin ambigüedad: tecnologías gratis y
    recursos iniciales. Nada se reordena ni se inventa.
    """
    if not civ:
        return []
    ajustes: list[tuple[str, str]] = []
    for b in (bonos["civs"].get(civ) or {}).get("bonos", []):
        efecto = b.get("efecto") or {}
        if b["tipo"] == "tech_gratis":
            for tech in efecto.get("techs", []):
                ajustes.append((
                    tech.lower(),
                    f"No la investigues: te sale gratis por «{b['texto_en']}»",
                ))
        elif b["tipo"] == "descuento_tech" and efecto.get("descuento") == 1.0:
            for tech in efecto.get("techs", []):
                ajustes.append((
                    tech.lower(),
                    f"Te cuesta menos de lo que dice el build: «{b['texto_en']}»",
                ))
    return ajustes


# --- Cálculos y plan B --------------------------------------------------------


def calculos_de(
    con: duckdb.DuckDBPyConnection, estrategia_id: str, civ: str | None, build: BuildOrder | None
) -> list[Calculo]:
    estrategias, bonos, _ = cargar_ref()
    e = next(x for x in estrategias["estrategias"] if x["id"] == estrategia_id)
    salida: list[Calculo] = []

    # 1. La unidad de la estrategia contra su counter esperado.
    if e.get("unidad_principal") and e.get("counter_esperado"):
        c = aritmetica.costo_efectividad(con, e["counter_esperado"], e["unidad_principal"])
        if c:
            salida.append(c)

    # 2. Amortización de la tech económica del recurso que más usa el build.
    if build:
        ultimo = build.pasos[-1] if build.pasos else None
        leñadores = (ultimo.wood if ultimo else 0) or 0
        if leñadores >= 3:
            c = aritmetica.amortizacion_tech(con, "Double-Bit Axe", leñadores)
            if c:
                salida.append(c)

    # 3. Cuánto vale el bono económico de la civ a los 10 minutos.
    for b in (bonos["civs"].get(civ) or {}).get("bonos", []) if civ else []:
        if b["tipo"] == "gather_rate":
            efecto = b["efecto"]
            c = aritmetica.valor_bono_gather(con, efecto["tarea"], efecto["multiplicador"], 6, 10)
            if c:
                c.supuestos.append(f"bono citado: «{b['texto_en']}»")
                salida.append(c)
            break
    return salida


def plan_b(con: duckdb.DuckDBPyConnection, estrategia_id: str) -> list[Senal]:
    estrategias, _, _ = cargar_ref()
    e = next(x for x in estrategias["estrategias"] if x["id"] == estrategia_id)
    salida = []
    nombres = {x["id"]: x["nombre"] for x in estrategias["estrategias"]}
    for s in e.get("señales", []):
        respaldo = None
        motivo = s.get("motivo", "")
        if s.get("motivo_counter"):
            unidad, contra = s["motivo_counter"]
            c = aritmetica.costo_efectividad(con, unidad, contra)
            if c:
                motivo = motivo or c.resultado
                respaldo = c.formula.split("\n")[0]
        salida.append(Senal(
            si_ves=s["si_ves"],
            transicionar_a=nombres.get(s["transicionar_a"], s["transicionar_a"]),
            motivo=motivo,
            respaldo=respaldo,
        ))
    return salida


# --- Armado del reporte -------------------------------------------------------


def recomendar(con: duckdb.DuckDBPyConnection, ctx: Contexto) -> Reporte:
    bucket = elo_bucket(ctx.elo)
    perfil = ev.perfil_mapa(con, ctx.mapa)
    ranking = puntuar(con, ctx, bucket, perfil)
    mejor = ranking[0] if ranking else None

    # Sin civ elegida: primero se ve qué plan pide el mapa, después qué civ lo acompaña mejor,
    # y recién ahí se rehace el ranking con esa civ para que el resto del reporte sea coherente.
    civs_sugeridas: list[CivSugerida] = []
    if ctx.civ is None:
        civs_sugeridas = sugerir_civs(con, ctx, bucket, mejor.id if mejor else None)
        if civs_sugeridas:
            ctx = ctx.model_copy(update={"civ": civs_sugeridas[0].civ})
            ranking = puntuar(con, ctx, bucket, perfil)
            mejor = ranking[0] if ranking else None

    analisis: dict[str, Evidencia] = {}
    if ctx.civ:
        analisis["mi civ en este mapa"] = Evidencia(**ev.civ_en_mapa(con, ctx.civ, ctx.mapa, bucket))
        for tramo, e in ev.por_duracion(con, ctx.civ, bucket).items():
            analisis[f"partidas {tramo}"] = Evidencia(**e)
    if ctx.civ and ctx.civ_rival:
        analisis["matchup"] = Evidencia(**ev.matchup(con, ctx.civ, ctx.civ_rival, bucket))
        analisis["la civ rival en este mapa"] = Evidencia(
            **ev.civ_en_mapa(con, ctx.civ_rival, ctx.mapa, bucket)
        )

    citas_civ = bonos_de_civ(con, ctx.civ)

    build = elegir_build(con, mejor.id, ctx.civ, bucket, ctx.mapa) if mejor else None
    return Reporte(
        contexto=ctx,
        elo_bucket=bucket,
        advertencias=advertencias(con, ctx, perfil),
        perfil_mapa=perfil,
        analisis_matchup=analisis,
        civ_bonos=citas_civ,
        estrategia=mejor,
        alternativas=ranking[1:3],
        civs_sugeridas=civs_sugeridas,
        build=build,
        calculos=calculos_de(con, mejor.id, ctx.civ, build) if mejor else [],
        plan_b=plan_b(con, mejor.id) if mejor else [],
    )


# --- Qué civ elegir -----------------------------------------------------------


def sugerir_civs(
    con: duckdb.DuckDBPyConnection,
    ctx: Contexto,
    bucket: str,
    estrategia_id: str | None = None,
    top: int = 6,
) -> list[CivSugerida]:
    """Ranking de civs para este mapa y tramo, cuando no fijaste la tuya.

    Mismo criterio que el resto del motor: se puntúa por el piso del intervalo, así una civ
    con poca muestra no trepa por casualidad. Las civs sin datos quedan afuera —no se puede
    recomendar lo que no se midió— y se avisa aparte cuáles son.
    """
    _, bonos, cfg = cargar_ref()
    pesos = cfg["pesos"]
    candidatas = [
        c[0]
        for c in con.execute(
            "SELECT DISTINCT civ FROM mart_civ_performance WHERE patch = ?", [DATA_PATCH]
        ).fetchall()
        if c[0] not in CIVS_SIN_DATOS and c[0] not in CIVS_SIN_DATOS_EN_FUENTE
    ]

    salida: list[CivSugerida] = []
    for civ in candidatas:
        e_civ = Evidencia(**ev.civ_en_mapa(con, civ, ctx.mapa, bucket))
        if e_civ.valor is None:
            continue
        piso = valor_prudente(e_civ)
        componentes = [Componente(
            nombre="rendimiento en el mapa",
            puntos=(piso - 0.5) * 100 * pesos["apertura"],
            detalle=f"{civ} en {ctx.mapa}: {e_civ.texto()}",
            evidencia=e_civ,
        )]
        if e_civ.nota:
            componentes.append(Componente(
                nombre="el dato no es de tu contexto",
                puntos=-pesos["evidencia_degradada"],
                detalle=e_civ.nota,
            ))

        bonos_civ = (bonos["civs"].get(civ) or {}).get("bonos", [])
        if estrategia_id and bonos_civ:
            afin, citas = _afinidad(bonos_civ, estrategia_id)
            if afin > 0:
                # Informativo, NO suma puntos: sólo 16 de 53 civs tienen los bonos modelados,
                # así que puntuarlo le daría una ventaja estructural a las que alcancé a
                # cargar. El orden lo decide el rendimiento medido, que no tiene ese sesgo.
                componentes.append(Componente(
                    nombre="además, acompaña el plan del mapa",
                    puntos=0.0,
                    detalle=f"bonos que empujan esa estrategia: {'; '.join(citas)}",
                ))

        if ctx.civ_rival:
            e_mu = Evidencia(**ev.matchup(con, civ, ctx.civ_rival, bucket))
            if e_mu.valor is not None:
                componentes.append(Componente(
                    nombre=f"contra {ctx.civ_rival}",
                    puntos=(valor_prudente(e_mu) - 0.5) * 100 * pesos["matchup_civ"],
                    detalle=e_mu.texto(),
                    evidencia=e_mu,
                ))

        # Los bonos salen del texto del juego (las 53 civs), no del YAML modelado (16).
        from aoe2coach.engine.civ import resumen_corto

        salida.append(CivSugerida(
            civ=civ,
            score=round(sum(c.puntos for c in componentes), 2),
            componentes=componentes,
            bonos=resumen_corto(con, civ),
        ))

    return sorted(salida, key=lambda x: x.score, reverse=True)[:top]
