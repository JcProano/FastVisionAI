"""Dependency-free responsive HTML; no external assets or executable script."""
from __future__ import annotations
from html import escape

WARNING = "Este dashboard sin autenticación web está diseñado exclusivamente para localhost o una LAN privada confiable. No exponer directamente a Internet."
NAV = (("/","⌂  Dashboard"),("/camera","◉  Cámara"),("/people","♙  Personas"),("/attendance","✓  Asistencia"),("/history","◷  Historial"),("/reports","▤  Reportes"),("/backups","▣  Backups"),("/audit","◌  Auditoría"),("/diagnostics","⌁  Diagnóstico"),("/settings","⚙  Configuración"))


def page(title: str, content: str, *, refresh: int | None = None) -> bytes:
    meta = "" if refresh is None else f'<meta http-equiv="refresh" content="{int(refresh)}">'
    nav = "".join(f'<a class="{"active" if title.casefold() in label.casefold() else ""}" href="{path}">{escape(label)}</a>' for path,label in NAV)
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{escape(title)} — FastVision AI</title><style>
:root{{color-scheme:dark;--bg:#07111f;--panel:#101c2e;--panel2:#14233a;--line:#263b57;--text:#edf4ff;--muted:#9db0c8;--accent:#4aa3ff;--ok:#37d39a;--warn:#f7bd4a;--bad:#ff6d7c}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 80% 0,#142b47,var(--bg) 45%);color:var(--text);font:14px Inter,ui-sans-serif,system-ui,sans-serif}}.shell{{min-height:100vh;display:grid;grid-template-columns:238px 1fr}}header{{grid-column:1/-1;display:flex;align-items:center;gap:18px;padding:15px 24px;background:#0b1728eF;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}}header h1{{font-size:18px;letter-spacing:.12em;margin:0}}header .mode{{color:var(--muted);font-size:12px}}.live{{margin-left:auto;display:flex;gap:12px;color:var(--muted)}}.live b{{color:var(--ok)}}aside{{padding:14px;border-right:1px solid var(--line);background:#0b1728}}nav{{display:grid;gap:5px}}a{{color:var(--muted);text-decoration:none;padding:11px 13px;border-radius:8px;font-weight:600}}a:hover,a.active{{background:#193154;color:#fff}}main{{max-width:1500px;width:100%;padding:24px;margin:auto}}h2{{font-size:24px;margin:0 0 18px}}h3{{margin-top:0;font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:#c9ddf8}}.banner{{margin:0 0 16px;padding:9px 12px;border:1px solid #6b5427;background:#2b2416;color:#ffd985;border-radius:8px;font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:14px 0}}.card,section{{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 12px 30px #0002}}.value{{font-size:32px;font-weight:700;color:#fff;margin-top:8px}}.columns{{display:grid;grid-template-columns:minmax(360px,1.55fr) minmax(320px,1fr);gap:14px}}.columns>div{{display:grid;gap:14px;align-content:start}}img.video{{width:100%;min-height:300px;border-radius:9px;object-fit:contain;background:#040b15}}table{{width:100%;border-collapse:collapse}}th{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.07em}}th,td{{padding:11px 8px;border-bottom:1px solid var(--line);text-align:left}}tr:last-child td{{border:0}}.scroll{{overflow:auto}}small{{color:var(--muted)}}button,input,select{{font:inherit;border-radius:7px;padding:8px 10px;border:1px solid var(--line)}}button{{background:#1e5fa8;color:#fff;border-color:#397cc3;cursor:pointer;margin:3px 2px}}button:hover{{background:#2875c9}}input,select{{background:#091421;color:#fff;margin:3px 8px 8px 3px}}.empty{{padding:28px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:9px}}.badge{{display:inline-block;padding:3px 8px;border-radius:999px;background:#173a32;color:var(--ok);font-size:11px;font-weight:700}}#camera-message{{min-height:20px;color:var(--warn)}}@media(max-width:850px){{.shell{{grid-template-columns:1fr}}header{{position:relative;flex-wrap:wrap}}aside{{border-right:0;border-bottom:1px solid var(--line);padding:8px}}nav{{display:flex;overflow:auto}}nav a{{white-space:nowrap}}.columns{{grid-template-columns:1fr}}main{{padding:14px}}.live{{margin-left:0;width:100%}}}}
</style></head><body><div class="shell"><header><h1>FASTVISION AI</h1><span class="mode">MODO APPLIANCE — RED LOCAL</span><span class="live"><span>● Cámara <b id="camera-live">en vivo</b></span><span>● Runtime <b id="runtime-live">ready</b></span><time id="clock"></time></span></header><aside><nav>{nav}</nav></aside><main><p class="banner">{escape(WARNING)}</p><h2>{escape(title)}</h2>{content}</main></div><script>setInterval(()=>document.getElementById('clock').textContent=new Date().toLocaleString(),1000)</script></body></html>'''.encode("utf-8")


def table(headers: tuple[str,...], rows: tuple[tuple[object,...],...]) -> str:
    head="".join(f"<th>{escape(str(item))}</th>" for item in headers)
    if not rows:return '<div class="empty">No hay registros para mostrar.</div>'
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
