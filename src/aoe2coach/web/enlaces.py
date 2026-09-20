"""Cómo se arma cada enlace, según dónde viva la app.

Las mismas plantillas sirven dos mundos: el servidor local (URLs con querystring, contenido
calculado al vuelo) y el sitio estático de GitHub Pages (archivos .html sueltos, todo
pregenerado). En vez de duplicar las plantillas, la función `u()` resuelve el enlace según el
modo y se inyecta en el entorno de Jinja.
"""

from __future__ import annotations


def url_servidor(tipo: str, **kw) -> str:
    if tipo == "inicio":
        return "/"
    if tipo == "datos":
        mapa, bucket = kw.get("mapa"), kw.get("bucket")
        if mapa or bucket:
            return f"/datos?mapa={mapa or 'all'}&bucket={bucket or 'all'}"
        return "/datos"
    if tipo == "civ":
        return f"/civ/{kw['civ']}?bucket={kw.get('bucket', 'all')}"
    if tipo == "checklist":
        return f"/checklist/{kw['build_id']}"
    if tipo == "reporte":
        return f"/reporte?mapa={kw['mapa']}&elo={kw.get('elo', 1000)}&civ={kw.get('civ', '')}"
    if tipo == "estilo":
        return "/static/estilo.css"
    if tipo == "js":
        return "/static/checklist.js"
    raise ValueError(f"enlace desconocido: {tipo}")


def url_estatica(tipo: str, **kw) -> str:
    """Todo plano en la raíz del sitio: evita líos de rutas relativas entre subcarpetas."""
    if tipo == "inicio":
        return "index.html"
    if tipo == "datos":
        return f"datos-{kw.get('mapa') or 'all'}-{kw.get('bucket') or 'all'}.html"
    if tipo == "civ":
        return f"civ-{kw['civ']}-{kw.get('bucket', 'all')}.html"
    if tipo == "checklist":
        return f"checklist-{kw['build_id']}.html"
    if tipo == "reporte":
        civ = kw.get("civ") or "recomendada"
        return f"reporte-{kw['mapa']}-{kw['bucket']}-{civ}.html"
    if tipo == "estilo":
        return "estilo.css"
    if tipo == "js":
        return "checklist.js"
    raise ValueError(f"enlace desconocido: {tipo}")
