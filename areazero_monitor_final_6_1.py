import os
#!/usr/bin/env python3
"""
areazero.biz - Monitor de Novedades v6
Dashboard HTML interactivo + email de aviso
"""

import json
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
    "sender_email": "ivanareazero@gmail.com",
    "sender_password": "xpgojcalxvhxmswp",
    "sender_name": "areazero Monitor",
    "recipients": [
        "ivanareazero@gmail.com",
        "soyblancassanchez@gmail.com",
        "cibersalva@gmail.com",
        "pedidosareazero@gmail.com",
        "alvaroareazero@gmail.com",
    ],
    "state_file": "areazero_products_state.json",
    "dashboard_file": "areazero_dashboard.html",
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
                price = ""
                variants = p.get("variants", [])
                if variants:
                    raw = variants[0].get("price", "")
                    try:
                        price = "{:.2f} EUR".format(float(raw))
                    except:
                        price = raw
                image_url = ""
                imgs = p.get("images", [])
                if imgs:
                    src = imgs[0].get("src", "")
                    if src:
                        image_url = src.split("?")[0] + "?width=400"
                products.append({
                    "handle": p.get("handle", pid),
                    "title": p.get("title", ""),
                    "brand": p.get("vendor", "Otros"),
                    "url": "{}/products/{}".format(CONFIG["base_url"], p.get("handle", "")),
                    "price": price,
                    "image_url": image_url,
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
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"products": {}, "last_check": None}


def save_state(products, state):
    existing = state.get("products", {})
    merged = {}
    for p in products:
        h = p["handle"]
        merged[h] = existing[h] if h in existing else p
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
    from datetime import datetime
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    total = len(products)
    total_new = len(new_handles)
    P = json.dumps(products, ensure_ascii=True, separators=(",",":"))
    N = json.dumps(list(new_handles), ensure_ascii=True, separators=(",",":"))
    BRANDS = "\n".join(
        '<option value="{b}">{b}</option>'.format(b=b.replace('"','&quot;'))
        for b in sorted(all_brands, key=lambda x: x.lower())
    )

    css = """*{margin:0;padding:0;box-sizing:border-box;}
body{background:#f5f5f5;color:#111;font-family:Helvetica,Arial,sans-serif;}
#lock{position:fixed;top:0;left:0;width:100%;height:100%;background:#fff;z-index:9999;display:flex;align-items:center;justify-content:center;}
.lbox{background:#fff;border:1px solid #ddd;border-radius:14px;padding:48px 40px;text-align:center;width:340px;}
.ltitle{font-size:44px;font-weight:900;color:#cc0000;letter-spacing:4px;text-transform:uppercase;}
.lsub{font-size:11px;color:#444;letter-spacing:3px;text-transform:uppercase;margin:8px 0 32px;}
#lpwd{width:100%;background:#fff;border:1px solid #ddd;color:#111;padding:12px;border-radius:8px;font-size:16px;outline:none;text-align:center;margin-bottom:12px;}
#lbtn{width:100%;background:#cc0000;color:#111;border:none;padding:14px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;}
#lerr{color:#cc0000;font-size:12px;margin-top:10px;display:none;}
.hdr{background:#fff;border-bottom:3px solid #f00;padding:18px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
.logo{font-size:38px;font-weight:900;color:#cc0000;text-transform:uppercase;letter-spacing:4px;line-height:1;}
.logo span{display:block;font-size:10px;font-weight:400;color:#444;letter-spacing:3px;margin-top:2px;}
.stats{display:flex;gap:12px;padding:20px 32px;flex-wrap:wrap;}
.stat{background:#f8f8f8;border:1px solid #ddd;border-radius:10px;padding:14px 22px;text-align:center;min-width:100px;}
.sn{font-size:28px;font-weight:700;} .sn.r{color:#cc0000;}
.sl{font-size:9px;color:#666;text-transform:uppercase;letter-spacing:2px;margin-top:2px;}
.flt{padding:0 32px 16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
.flt select,.flt input{background:#f8f8f8;border:1px solid #ddd;color:#111;padding:8px 12px;border-radius:8px;font-size:12px;outline:none;}
.flt input{min-width:180px;}
.btn{border:none;padding:8px 16px;border-radius:8px;font-size:11px;font-weight:700;cursor:pointer;text-transform:uppercase;}
.br{background:#cc0000;color:#111;} .bd{background:#f8f8f8;border:1px solid #ddd;color:#111;}
.leg{padding:0 32px 14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
.leg span{font-size:10px;color:#444;}
.pill{font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;color:#111;}
.xbar{padding:0 32px 14px;display:flex;gap:8px;}
.brands{padding:0 32px 60px;}
.bsec{background:#fff;border:1px solid #ddd;border-radius:12px;margin-bottom:10px;overflow:hidden;}
.bhdr{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;cursor:pointer;user-select:none;}
.bhdr:hover{background:#fff;}
.bhl{display:flex;align-items:center;gap:10px;}
.bnm{font-size:16px;font-weight:700;text-transform:uppercase;letter-spacing:2px;}
.bcnt{background:#cc0000;color:#111;font-size:11px;font-weight:700;padding:3px 9px;border-radius:20px;}
.bnew{background:#00c97a;color:#111;font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;}
.barr{color:#cc0000;font-size:16px;transition:transform 0.2s;}
.bbody{padding:16px;display:none;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;overflow:hidden;position:relative;transition:border-color 0.15s;}
.card:hover{border-color:#cc0000;} .card.isnew{border-color:#00c97a;}
.cimg{width:100%;height:190px;object-fit:cover;display:block;background:#eeeeee;}
.nimg{width:100%;height:190px;background:#eeeeee;display:flex;align-items:center;justify-content:center;color:#444;font-size:11px;}
.ab{position:absolute;top:8px;right:8px;font-size:10px;font-weight:700;padding:3px 8px;border-radius:20px;color:#111;}
.np{position:absolute;top:8px;left:8px;background:#00c97a;color:#111;font-size:10px;font-weight:700;padding:3px 8px;border-radius:20px;}
.ci{padding:12px;} .cbr{font-size:9px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#cc0000;margin-bottom:3px;}
.ct{font-size:13px;font-weight:600;color:#111;line-height:1.3;margin-bottom:6px;}
.cp{font-size:18px;font-weight:700;color:#cc0000;margin-bottom:8px;}
.cl{display:inline-block;padding:6px 14px;background:#cc0000;color:#111;text-decoration:none;border-radius:6px;font-size:10px;font-weight:700;text-transform:uppercase;}
.empty{text-align:center;padding:60px;color:#444;}"""

    js = """
document.getElementById("lbtn").addEventListener("click",function(){
  var p=document.getElementById("lpwd").value;
  if(p==="areazero2026"){
    document.getElementById("lock").style.display="none";
    document.getElementById("app").style.display="block";
    run();
  }else{
    document.getElementById("lerr").style.display="block";
    document.getElementById("lpwd").value="";
  }
});
document.getElementById("lpwd").addEventListener("keydown",function(e){
  if(e.key==="Enter") document.getElementById("lbtn").click();
});
function da(s){try{var a=new Date(s),b=new Date();a.setHours(0,0,0,0);b.setHours(0,0,0,0);return Math.round((b-a)/86400000);}catch(e){return 0;}}
function ai(d){if(d<=0)return{l:"Hoy",c:"#00c97a"};if(d===1)return{l:"Ayer",c:"#00c97a"};if(d<=7)return{l:d+" dias",c:"#f5a623"};if(d<=14)return{l:d+" dias",c:"#ff6b35"};return{l:d+" dias",c:"#c00"};}
function pr(s){return s?parseFloat(s.replace("EUR","").replace(",",".").trim())||0:0;}
function mk(p){
  var d=da(p.found_at),a=ai(d),isN=N.indexOf(p.handle)!==-1;
  var img=p.image_url?'<img class="cimg" src="'+p.image_url+'" loading="lazy">':'<div class="nimg">Sin imagen</div>';
  var np=isN?'<div class="np">NUEVO</div>':"";
  var pr2=p.price?'<div class="cp">'+p.price+'</div>':"";
  return '<div class="card'+(isN?" isnew":"")+'"><div style="position:relative">'+img+np+'<span class="ab" style="background:'+a.c+'">'+a.l+'</span></div><div class="ci"><div class="cbr">'+p.brand+'</div><div class="ct">'+p.title+'</div>'+pr2+'<a class="cl" href="'+p.url+'" target="_blank">Ver producto</a></div></div>';
}
function tog(el){
  var i=el.getAttribute("data-i");
  var b=document.getElementById("b"+i),ar=document.getElementById("a"+i);
  if(!b)return;
  var o=b.style.display==="block";
  b.style.display=o?"none":"block";
  ar.style.transform=o?"rotate(0)":"rotate(180deg)";
}
function xall(v){
  document.querySelectorAll(".bbody").forEach(function(e){e.style.display=v?"block":"none";});
  document.querySelectorAll(".barr").forEach(function(e){e.style.transform=v?"rotate(180deg)":"rotate(0)";});
}
function run(){
  var fb=document.getElementById("fb").value,fa=document.getElementById("fa").value,fs=document.getElementById("fs").value,fq=document.getElementById("fq").value.toLowerCase().trim();
  var list=P.filter(function(p){
    if(fb&&p.brand!==fb)return false;
    if(fa!==""&&da(p.found_at)>parseInt(fa))return false;
    if(fq&&(p.title+" "+p.brand).toLowerCase().indexOf(fq)===-1)return false;
    return true;
  });
  list.sort(function(a,b){
    if(fs==="new")return new Date(b.found_at)-new Date(a.found_at);
    if(fs==="old")return new Date(a.found_at)-new Date(b.found_at);
    if(fs==="pa")return pr(a.price)-pr(b.price);
    if(fs==="pd")return pr(b.price)-pr(a.price);
    return a.brand.localeCompare(b.brand);
  });
  var byB={};
  list.forEach(function(p){if(!byB[p.brand])byB[p.brand]=[];byB[p.brand].push(p);});
  var brs=Object.keys(byB).sort(function(a,b){return a.localeCompare(b);});
  var html="";
  brs.forEach(function(br,i){
    var prods=byB[br];
    var nc=prods.filter(function(p){return N.indexOf(p.handle)!==-1;}).length;
    var nb=nc>0?'<span class="bnew">+'+nc+' nuevos</span>':"";
    var dot=nc>0?'<span style="display:inline-block;width:10px;height:10px;background:#00c97a;border-radius:50%;margin-left:8px;"></span>':"";
    html+='<div class="bsec"><div class="bhdr" data-i="'+i+'" onclick="tog(this)"><div class="bhl"><span class="bnm">'+br+'</span><span class="bcnt">'+prods.length+'</span>'+nb+dot+'</div><span class="barr" id="a'+i+'" style="transform:rotate(0)">&#9660;</span></div><div class="bbody" id="b'+i+'" style="display:none"><div class="grid">'+prods.map(mk).join("")+'</div></div></div>';
  });
  document.getElementById("out").innerHTML=html||'<div class="empty">Sin resultados.</div>';
  document.getElementById("sm").textContent=list.length;
}
function reset(){
  document.getElementById("fb").value="";document.getElementById("fa").value="";
  document.getElementById("fs").value="new";document.getElementById("fq").value="";
  run();
}"""

    html = (
        '<!DOCTYPE html>\n<html lang="es"><head><meta charset="UTF-8">'
        '<title>AREA ZERO - Dashboard Novedades</title><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMiAzMiI+CiAgPGNpcmNsZSBjeD0iMTYiIGN5PSIxNiIgcj0iMTQiIGZpbGw9IiNmZjAwMDAiLz4KPC9zdmc+">'
        '<style>' + css + '</style></head><body>'
        '<div id="lock"><div class="lbox">'
        '<div class="ltitle">AREA ZERO</div>'
        '<div class="lsub">Monitor de Novedades</div>'
        '<input type="password" id="lpwd" placeholder="Contrasena">'
        '<button id="lbtn">Entrar</button>'
        '<div id="lerr">Contrasena incorrecta</div>'
        '</div></div>'
        '<div id="app" style="display:none">'
        '<div class="hdr"><div class="logo">AREA ZERO<span>Monitor de Novedades</span></div>'
        '<div style="font-size:11px;color:#444">' + now + '</div></div>'
        '<div class="stats">'
        '<div class="stat"><div class="sn">' + str(total) + '</div><div class="sl">Productos</div></div>'
        '<div class="stat"><div class="sn r">' + str(total_new) + '</div><div class="sl">Nuevos</div></div>'
        '<div class="stat"><div class="sn" id="sm">' + str(total) + '</div><div class="sl">Mostrando</div></div>'
        '</div>'
        '<div class="flt">'
        '<select id="fb" onchange="run()"><option value="">Todas las marcas</option>' + BRANDS + '</select>'
        '<select id="fa" onchange="run()"><option value="">Cualquier antiguedad</option>'
        '<option value="0">Hoy</option><option value="1">2 dias</option>'
        '<option value="7">Semana</option><option value="14">2 semanas</option></select>'
        '<select id="fs" onchange="run()"><option value="new">Mas nuevos primero</option>'
        '<option value="old">Mas antiguos</option><option value="pa">Precio menor</option>'
        '<option value="pd">Precio mayor</option><option value="az">Marca A-Z</option></select>'
        '<input id="fq" type="text" placeholder="Buscar..." oninput="run()">'
        '<button class="btn bd" onclick="reset()">Limpiar</button></div>'
        '<div class="leg"><span>Antiguedad:</span>'
        '<span class="pill" style="background:#00c97a">Hoy/Ayer</span>'
        '<span class="pill" style="background:#f5a623">2-7 dias</span>'
        '<span class="pill" style="background:#ff6b35">8-14 dias</span>'
        '<span class="pill" style="background:#aa0000">+15 dias</span></div>'
        '<div class="xbar"><button class="btn br" onclick="xall(1)">Expandir todo</button>'
        '<button class="btn bd" onclick="xall(0)">Colapsar todo</button></div>'
        '<div id="out" class="brands"></div>'
        '</div>'
        '<script>\nvar P=' + P + ';\nvar N=' + N + ';' + js + '\n</script>'
        '</body></html>'
    )
    return html


def send_alert_email(new_products):
    count = len(new_products)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    by_brand = defaultdict(list)
    for p in new_products:
        by_brand[p.get("brand", "Otros")].append(p)

    rows = "".join(
        '<tr><td style="padding:4px 0;color:#111;font-size:13px;">{}</td>'
        '<td style="text-align:right;"><span style="background:#cc0000;color:#111;'
        'font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;">{}</span></td></tr>'.format(b, len(ps))
        for b, ps in sorted(by_brand.items())
    )

    html = """<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#fff;font-family:Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 12px;">
<table width="500" cellpadding="0" cellspacing="0"
       style="max-width:500px;width:100%;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #ddd;">
<tr><td style="background:#1a0000;padding:26px;text-align:center;border-bottom:2px solid #f00;">
  <div style="font-size:10px;color:#cc0000;letter-spacing:4px;text-transform:uppercase;margin-bottom:6px;">NUEVAS NOVEDADES</div>
  <div style="font-size:24px;font-weight:900;color:#111;text-transform:uppercase;">AREA<span style="color:#cc0000;">ZERO</span></div>
</td></tr>
<tr><td style="padding:22px 26px;">
  <div style="text-align:center;margin-bottom:18px;">
    <div style="display:inline-block;background:#cc0000;color:#111;padding:8px 22px;border-radius:50px;font-size:14px;font-weight:700;">
      {count} nuevo{s} producto{s} detectado{s}
    </div>
    <div style="font-size:11px;color:#666;margin-top:7px;">{now}</div>
  </div>
  <div style="background:#fff;border-radius:9px;padding:14px 16px;margin-bottom:18px;">
    <div style="font-size:10px;color:#666;text-transform:uppercase;letter-spacing:1px;margin-bottom:9px;">Por marca</div>
    <table style="width:100%;">{rows}</table>
  </div>
  <div style="text-align:center;background:#eeeeee;border:1px solid #ddd;border-radius:8px;padding:12px;">
    <div style="font-size:12px;color:#888;margin-bottom:4px;">Abre tu dashboard para ver todos los detalles</div>
    <div style="font-size:12px;color:#111;font-weight:700;">areazero_dashboard.html</div>
    <div style="font-size:11px;color:#666;margin-top:3px;">Carpeta: AREA ZERO MONITOR</div>
  </div>
</td></tr>
<tr><td style="padding:12px 26px;text-align:center;border-top:1px solid #1a1a1a;">
  <div style="font-size:10px;color:#444;">Monitor automatico areazero.biz - {now}</div>
</td></tr>
</table></td></tr></table>
</body></html>""".format(
        count=count,
        s="s" if count != 1 else "",
        now=now,
        rows=rows,
    )

    subj = "{} nuevo{} producto{} en areazero.biz - {}".format(
        count, "s" if count != 1 else "", "s" if count != 1 else "",
        datetime.now().strftime("%d/%m/%Y"))
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = "{} <{}>".format(CONFIG["sender_name"], CONFIG["sender_email"])
    msg["To"] = ", ".join(CONFIG["recipients"])
    msg.attach(MIMEText(html, "html", "utf-8"))
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
    print("  Subiendo a GitHub Pages...")
    upload_to_github(html)

    if new_prods:
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
