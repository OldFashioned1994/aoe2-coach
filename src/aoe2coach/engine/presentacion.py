"""Render del reporte a texto. La web de la Fase 3 va a consumir el mismo `Reporte`."""

from __future__ import annotations

from aoe2coach.engine.modelos import Reporte

ANCHO = 84


def _titulo(t: str) -> str:
    return f"\n{t}\n{'─' * min(len(t), ANCHO)}"


def _mmss(segundos: float | None) -> str:
    if not segundos:
        return "-"
    return f"{int(segundos) // 60}:{int(segundos) % 60:02d}"


def render_texto(r: Reporte) -> str:
    out: list[str] = []
    ctx = r.contexto
    civ = ctx.civ or "civ sin definir"
    rival = f" contra {ctx.civ_rival}" if ctx.civ_rival else ""
    out.append("═" * ANCHO)
    out.append(f"  {civ.upper()}{rival.upper()} · {ctx.mapa} · Elo {ctx.elo} (tramo {r.elo_bucket})")
    out.append("═" * ANCHO)

    for a in r.advertencias:
        out.append(f"  ⚠  {a}")

    p = r.perfil_mapa
    if p.get("perfil") != "desconocido":
        detalle = f"{p['perfil']}, Fast Castle en el {p['fc_share'] * 100:.0f}% de las partidas"
        detalle += " (n=" + f"{p['n_aperturas']:,}".replace(",", ".") + ")"
        if p.get("agua") in ("si", "parcial"):
            detalle += f" · con agua ({p['naval_share'] * 100:.0f}% de aperturas navales en 2023)"
        out.append(_titulo("EL MAPA"))
        out.append(f"  {ctx.mapa}: {detalle}")
        out.append(f"  Perfil derivado de datos, no declarado a mano. {p['fuente']}")

    if r.civs_sugeridas:
        out.append(_titulo("QUÉ CIV ELEGIR"))
        out.append(f"  Para {ctx.mapa} en tu tramo de Elo, por orden de rendimiento medido:")
        for i, c in enumerate(r.civs_sugeridas, 1):
            marca = "→" if i == 1 else " "
            out.append(f"  {marca} {c.score:+6.2f}  {c.civ}")
            for comp in c.componentes:
                signo = f"{comp.puntos:+6.2f}" if comp.puntos else "      "
                out.append(f"              {signo}  {comp.nombre}: {comp.detalle}")
        out.append('\n  Se arma el plan con ' + r.civs_sugeridas[0].civ + ", la primera de la lista.")

    if r.analisis_matchup:
        out.append(_titulo("EL MATCHUP"))
        for etiqueta, e in r.analisis_matchup.items():
            out.append(f"  {etiqueta:<28} {e.texto()}")

    if r.civ_bonos:
        out.append(_titulo("TU CIV, SEGÚN EL JUEGO"))
        for b in r.civ_bonos:
            out.append(f"  · {b}")

    if r.estrategia:
        e = r.estrategia
        out.append(_titulo(f"ESTRATEGIA RECOMENDADA: {e.nombre.upper()}"))
        out.append(f"  {e.descripcion}")
        out.append(f"\n  Puntaje {e.score:+.2f}, así se compone:")
        for c in e.componentes:
            out.append(f"    {c.puntos:+6.2f}  {c.nombre}")
            out.append(f"            {c.detalle}")
        for a in e.advertencias:
            out.append(f"    ⚠  {a}")

    if r.alternativas:
        out.append(_titulo("ALTERNATIVAS"))
        for a in r.alternativas:
            out.append(f"  {a.score:+6.2f}  {a.nombre}")
            for c in a.componentes:
                if c.puntos:
                    out.append(f"            {c.puntos:+6.2f}  {c.nombre}: {c.detalle}")

    if r.build:
        b = r.build
        out.append(_titulo(f"BUILD ORDER: {b.nombre.upper()}"))
        out.append(f"  Autor: {b.autor} · Fuente: {b.fuente}")
        out.append(f"  ({b.nota_seleccion})")
        if b.uptime_esperado and b.uptime_esperado.valor:
            u = b.uptime_esperado
            rango = f" (mitad central {_mmss(u.ci[0])}–{_mmss(u.ci[1])})" if u.ci else ""
            out.append(
                f"  Uptime a Feudal de jugadores reales de tu nivel: {_mmss(u.valor)}{rango} · "
                + "n=" + f"{u.n:,}".replace(",", ".")
            )
            out.append(f"  {u.nota}")
        out.append("")
        for p in b.pasos:
            reparto = " ".join(
                f"{v}{s}" for v, s in
                ((p.food, "C"), (p.wood, "M"), (p.gold, "O"), (p.stone, "P")) if v
            )
            edad = {1: "Oscura", 2: "Feudal", 3: "Castillos", 4: "Imperial"}.get(p.age or 0, "")
            cabeza = f"  {p.tiempo or '':>5}  {str(p.villager_count or ''):>3} vill  {reparto:<16} {edad:<10}"
            out.append(cabeza + (p.notas[:120] if p.notas else ""))
            if p.ajuste_civ:
                out.append(f"         ↳ {p.ajuste_civ}")

    if r.calculos:
        out.append(_titulo("LA CUENTA DETRÁS"))
        for c in r.calculos:
            out.append(f"  {c.titulo}")
            out.append(f"    → {c.resultado}")
            for linea in c.formula.split("\n"):
                out.append(f"      {linea}")
            for s in c.supuestos:
                out.append(f"      · supuesto: {s}")
            out.append(f"      fuente: {c.fuente}")
            out.append("")

    if r.plan_b:
        out.append(_titulo("PLAN B: QUÉ MIRAR Y CÓMO ADAPTAR"))
        for s in r.plan_b:
            out.append(f"  Si ves {s.si_ves} → pasá a «{s.transicionar_a}»")
            if s.motivo:
                out.append(f"      {s.motivo}")
            if s.respaldo:
                out.append(f"      {s.respaldo}")

    out.append("")
    return "\n".join(out)
