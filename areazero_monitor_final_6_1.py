#!/usr/bin/env python3
"""
areazero.biz - Monitor de Novedades v6
Dashboard HTML interactivo + email de aviso
"""

import json
import os
import smtplib
import time
from collections import defaultdict
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

CONFIG = {
    "base_url": "https://areazero.biz",
    "collection_handle": "novedades",
    "pages_to_check": 10,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": os.environ.get("GMAIL_USER", "ivanareazero@gmail.com"),
    "sender_password": os.environ.get("GMAIL_PASS", ""),
    "sender_name": "areazero Monitor",
    "recipients": [
        "ivanareazero@gmail.com",
        "soyblancassanchez@gmail.com",
        "cibersalva@gmail.com",
        "pedidosareazero@gmail.com",
        "alvaroareazero@gmail.com",
    ],
    "state_file": "areazero_products_state.json",
    "dashboard_file": "index.html",
    "send_if_no_changes": False,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


GITHUB = {
    "token": os.environ.get("GH_TOKEN", "GITHUB_TOKEN_HERE"),
    "user": "ivanareazero-eng",
    "repo": "areazero-novedades",
    "file": "index.html",
}

def upload_to_github(html_content):
    """Sube el dashboard a GitHub Pages automaticamente."""
    try:
        from github import Github
        g = Github(GITHUB["token"])
        repo = g.get_repo("{}/{}".format(GITHUB["user"], GITHUB["repo"]))
        encoded = html_content.encode("utf-8")
        try:
            existing = repo.get_contents(GITHUB["file"])
            repo.update_file(GITHUB["file"], "Actualizar dashboard novedades", encoded, existing.sha)
        except Exception:
            repo.create_file(GITHUB["file"], "Crear dashboard novedades", encoded)
        print("  Dashboard subido a: https://{}.github.io/{}/".format(GITHUB["user"], GITHUB["repo"]))
        return True
    except Exception as e:
        print("  Error subiendo a GitHub: {}".format(e))
        return False


def fetch_all_brands():
    print("  -> Obteniendo todas las marcas...")
    brands = set()
    page = 1
    while True:
        url = "{}/products.json?limit=250&page={}".format(CONFIG["base_url"], page)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            prods = resp.json().get("products", [])
            if not prods:
                break
            for p in prods:
                v = p.get("vendor", "").strip()
                if v:
                    brands.add(v)
            if len(prods) < 250:
                break
            page += 1
            time.sleep(1)
        except Exception as e:
            print("  Error marcas pagina {}: {}".format(page, e))
            break
    result = sorted(brands, key=lambda b: b.lower())
    print("    Marcas: {}".format(len(result)))
    return result


def fetch_products():
    products = []
    seen = set()
    for page in range(1, 20):
        url = "{}/collections/{}/products.json?limit=250&page={}".format(
            CONFIG["base_url"], CONFIG["collection_handle"], page)
        print("  -> Pagina {}".format(page))
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            page_prods = resp.json().get("products", [])
            print("    Encontrados: {}".format(len(page_prods)))
            if not page_prods:
                break
            for p in page_prods:
                pid = str(p.get("id", ""))
                if pid in seen:
                    continue
                seen.add(pid)
                variants = p.get("variants", []) or []
                prices, compares = [], []
                for v in variants:
                    try:
                        prices.append(float(v.get("price") or 0))
                    except Exception:
                        pass
                    try:
                        c = float(v.get("compare_at_price") or 0)
                        if c:
                            compares.append(c)
                    except Exception:
                        pass
                price = min(prices) if prices else 0
                compare = max(compares) if compares else 0
                sizes = [v.get("option1") or "" for v in variants if v.get("available")]
                image_url = ""
                imgs = p.get("images", [])
                if imgs:
                    src = imgs[0].get("src", "")
                    if src:
                        image_url = src.split("?")[0] + "?width=500"
                products.append({
                    "handle": p.get("handle", pid),
                    "title": p.get("title", ""),
                    "brand": (p.get("vendor") or "Otros").strip(),
                    "type": p.get("product_type", ""),
                    "url": "{}/products/{}".format(CONFIG["base_url"], p.get("handle", "")),
                    "price": round(price, 2),
                    "compare": round(compare, 2) if compare > price else 0,
                    "available": any(v.get("available") for v in variants),
                    "sizes": [x for x in sizes if x and x.lower() != "default title"][:12],
                    "image_url": image_url,
                    "created_at": p.get("created_at") or p.get("published_at") or "",
                    "found_at": datetime.now().isoformat(),
                })
            if len(page_prods) < 250:
                break
            time.sleep(1)
        except Exception as e:
            print("  Error pagina {}: {}".format(page, e))
            break
    return products


def load_state():
    path = Path(CONFIG["state_file"])
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("products"), dict):
                data.setdefault("last_check", None)
                return data
            print("  Estado no valido, se empieza de cero.")
        except Exception as e:
            print("  No se pudo leer el estado ({}), se empieza de cero.".format(e))
    return {"products": {}, "last_check": None}


def save_state(products, state):
    existing = state.get("products", {})
    merged = {}
    for p in products:
        h = p["handle"]
        merged[h] = p
    with open(CONFIG["state_file"], "w", encoding="utf-8") as f:
        json.dump({"products": merged, "last_check": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)


def enrich_dates(products, state):
    stored = state.get("products", {})
    for p in products:
        if p["handle"] in stored:
            p["found_at"] = stored[p["handle"]].get("found_at", p["found_at"])
    return products


def find_new(current, state):
    known = set(state.get("products", {}).keys())
    if not known:
        return []
    return [p for p in current if p["handle"] not in known]


def build_dashboard(products, new_handles, all_brands):
    """Rellena dashboard_template.html con los datos."""
    tpl = Path(__file__).with_name("dashboard_template.html").read_text(encoding="utf-8")
    data = {
        "products": products,
        "new": sorted(new_handles),
        "updated": datetime.now().astimezone().isoformat(),
    }
    blob = json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    return tpl.replace("__DATA__", blob)


def send_alert_email(new_products):
    from html import escape
    count = len(new_products)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    dash = "https://ivanareazero-eng.github.io/areazero-novedades/"
    by_brand = defaultdict(list)
    for p in new_products:
        by_brand[p.get("brand", "Otros")].append(p)
    brands_txt = ", ".join("{} ({})".format(escape(b), len(ps)) for b, ps in sorted(by_brand.items()))

    def eur(n):
        try:
            return "{:,.2f} \u20ac".format(float(n)).replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return ""

    cells = []
    for p in new_products[:12]:
        img = p.get("image_url") or ""
        price = eur(p.get("price")) if p.get("price") else ""
        cells.append(
            '<td width="50%" valign="top" style="padding:8px;">'
            '<a href="{url}" style="text-decoration:none;color:#17181A;">'
            '<img src="{img}" width="252" style="width:100%;max-width:252px;height:auto;display:block;border-radius:8px;background:#ffffff;" alt="">'
            '<div style="font:700 12px Arial,sans-serif;color:#A50F0B;margin-top:8px;">{brand}</div>'
            '<div style="font:14px/1.3 Arial,sans-serif;color:#17181A;margin-top:2px;">{title}</div>'
            '<div style="font:700 15px Arial,sans-serif;color:#17181A;margin-top:4px;">{price}</div>'
            '</a></td>'.format(url=escape(p.get("url", "")), img=escape(img), brand=escape(p.get("brand", "")),
                               title=escape(p.get("title", "")), price=price))
    rows = "".join("<tr>" + "".join(cells[i:i + 2]) + ("<td></td>" if len(cells[i:i + 2]) == 1 else "") + "</tr>"
                   for i in range(0, len(cells), 2))
    more = count - min(count, 12)
    more_txt = ('<p style="font:14px Arial,sans-serif;color:#676B70;margin:8px 0 0;text-align:center;">'
                'Y {} m\u00e1s en el panel.</p>'.format(more)) if more > 0 else ""

    html = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#EEEFEC;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEEFEC;"><tr><td align="center" style="padding:24px 12px;">
<table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
<tr><td style="background:#17181A;padding:20px 24px;">
  <span style="font:900 24px Impact,'Arial Black',Arial,sans-serif;color:#ffffff;letter-spacing:.5px;">AREA <span style="color:#D2140F;">ZERO</span></span>
  <span style="font:14px Arial,sans-serif;color:#B9BCC1;padding-left:10px;">Novedades</span>
</td></tr>
<tr><td style="padding:28px 24px 8px;">
  <div style="font:900 40px/1 Impact,'Arial Black',Arial,sans-serif;color:#17181A;">{count} {pl_new} en la web</div>
  <p style="font:15px/1.5 Arial,sans-serif;color:#676B70;margin:10px 0 0;">{brands}</p>
</td></tr>
<tr><td style="padding:12px 16px 4px;"><table width="100%" cellpadding="0" cellspacing="0">{rows}</table>{more}</td></tr>
<tr><td align="center" style="padding:20px 24px 28px;">
  <a href="{dash}" style="display:inline-block;background:#D2140F;color:#ffffff;font:700 15px Arial,sans-serif;text-decoration:none;padding:14px 26px;border-radius:8px;">Ver todas las novedades</a>
</td></tr>
<tr><td style="padding:14px 24px;border-top:1px solid #E4E5E2;font:12px Arial,sans-serif;color:#8A8E93;">
  Aviso autom\u00e1tico del monitor de areazero.biz \u00b7 {now}
</td></tr>
</table></td></tr></table>
</body></html>""".format(count=count, pl_new="producto nuevo" if count == 1 else "productos nuevos",
                         brands=brands_txt, rows=rows, more=more_txt, dash=dash, now=now)

    subj = "{} nuevo{} producto{} en areazero.biz - {}".format(
        count, "s" if count != 1 else "", "s" if count != 1 else "",
        datetime.now().strftime("%d/%m/%Y"))
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = "{} <{}>".format(CONFIG["sender_name"], CONFIG["sender_email"])
    msg["To"] = ", ".join(CONFIG["recipients"])
    msg.attach(MIMEText(html, "html", "utf-8"))
    if not CONFIG["sender_password"]:
        print("  Sin GMAIL_PASS configurado: no se envia email.")
        return False
    try:
        with smtplib.SMTP(CONFIG["smtp_host"], CONFIG["smtp_port"]) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(CONFIG["sender_email"], CONFIG["sender_password"])
            srv.sendmail(CONFIG["sender_email"], CONFIG["recipients"], msg.as_string())
        print("  Email enviado a: {}".format(", ".join(CONFIG["recipients"])))
        return True
    except Exception as e:
        print("  Error email: {}".format(e))
        return False


def main():
    print("\n" + "="*55)
    print("areazero Monitor v6 - {}".format(datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    print("="*55)

    print("\n[1/5] Cargando estado...")
    state = load_state()
    if state["last_check"]:
        print("  Ultima vez: {} | Productos: {}".format(
            state["last_check"], len(state.get("products", {}))))
    else:
        print("  Primera ejecucion.")

    print("\n[2/5] Obteniendo marcas de la tienda...")
    all_brands = fetch_all_brands()

    print("\n[3/5] Obteniendo productos de novedades...")
    current = fetch_products()
    print("  Total: {}".format(len(current)))
    if not current:
        print("  Sin productos. Intentalo de nuevo.")
        return

    current = enrich_dates(current, state)

    print("\n[4/5] Detectando novedades...")
    new_prods = find_new(current, state)
    new_handles = set(p["handle"] for p in new_prods)

    if not state.get("products"):
        save_state(current, state)
        print("  Estado inicial: {} productos guardados.".format(len(current)))
    else:
        print("  Nuevos: {}".format(len(new_prods)))
        for p in new_prods:
            print("    - [{}] {}".format(p["brand"], p["title"]))
        save_state(current, state)

    print("\n[5/5] Generando dashboard...")
    html = build_dashboard(current, new_handles, all_brands)
    path = Path(CONFIG["dashboard_file"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  Guardado: {}".format(path.resolve()))

    if os.environ.get("TEST_EMAIL") == "1":
        print("  Email de PRUEBA (solo al remitente)...")
        CONFIG["recipients"] = [CONFIG["sender_email"]]
        send_alert_email(current[:3])
    elif new_prods:
        print("  Enviando email...")
        send_alert_email(new_prods)
    elif CONFIG["send_if_no_changes"]:
        send_alert_email([])
    else:
        print("  Sin novedades, no se envia email.")

    print("\n Listo. Abre areazero_dashboard.html en el navegador.")
    print("="*55 + "\n")


if __name__ == "__main__":
    main()
