"""Dependency-free responsive HTML; no external assets or executable script."""
from __future__ import annotations
from html import escape

WARNING = "Este dashboard sin autenticación web está diseñado exclusivamente para localhost o una LAN privada confiable. No exponer directamente a Internet."
NAV = (("/","Dashboard"),("/camera","Cámara"),("/people","Personas"),("/attendance","Asistencia"),("/history","Historial"),("/reports","Reportes"),("/backups","Backups"),("/audit","Auditoría"),("/diagnostics","Diagnóstico"),("/settings","Configuración"))


def page(title: str, content: str, *, refresh: int | None = None) -> bytes:
    meta = "" if refresh is None else f'<meta http-equiv="refresh" content="{int(refresh)}">'
    nav = "".join(f'<a href="{path}">{escape(label)}</a>' for path,label in NAV)
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{escape(title)} — FastVision AI</title><style>
body{{margin:0;background:#07101f;color:#e5e7eb;font:15px system-ui,sans-serif}}header,main{{max-width:1400px;margin:auto;padding:16px}}header{{display:flex;gap:18px;align-items:center;flex-wrap:wrap}}nav{{display:flex;gap:8px;flex-wrap:wrap}}a{{color:#bfdbfe;text-decoration:none;padding:8px;border-radius:6px;background:#172554}}.banner{{padding:10px;background:#7c2d12;border-radius:8px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:14px 0}}.card,section{{background:#111827;border:1px solid #273449;border-radius:10px;padding:14px}}.value{{font-size:28px;color:#60a5fa}}.columns{{display:grid;grid-template-columns:minmax(280px,2fr) minmax(280px,1fr);gap:14px}}img.video{{width:100%;min-height:220px;object-fit:contain;background:#020617}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #273449;text-align:left}}.scroll{{overflow:auto}}small{{color:#94a3b8}}@media(max-width:800px){{.columns{{grid-template-columns:1fr}}header{{align-items:flex-start}}th,td{{white-space:nowrap}}}}
</style></head><body><header><h1>FASTVISION AI</h1><nav>{nav}</nav></header><main><p class="banner">MODO APPLIANCE — RED LOCAL</p><small>{escape(WARNING)}</small><h2>{escape(title)}</h2>{content}</main></body></html>'''.encode("utf-8")


def table(headers: tuple[str,...], rows: tuple[tuple[object,...],...]) -> str:
    head="".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body="".join("<tr>"+"".join(f"<td>{escape('' if item is None else str(item))}</td>" for item in row)+"</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def photo_table(headers: tuple[str,...], rows: tuple[tuple[object,...],...]) -> str:
    """Render only server-issued thumbnail URLs in the first column."""
    head="".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body=[]
    for row in rows:
        source=row[0] if row else None
        image=(f'<img src="{escape(source)}" width="44" height="44" alt="Foto">'
               if isinstance(source,str) and source.startswith("/api/thumbnails/") else "Sin foto")
        cells="<td>"+image+"</td>"+"".join(f"<td>{escape('' if item is None else str(item))}</td>" for item in row[1:])
        body.append("<tr>"+cells+"</tr>")
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
