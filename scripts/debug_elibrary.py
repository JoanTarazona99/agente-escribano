"""
Script de diagnóstico del conector eLIBRARY (movido a `scripts/`).
Ejectúalo desde la raíz del proyecto:
  python scripts/debug_elibrary.py
"""
import os, sys, time, re
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django
django.setup()

try:
    from curl_cffi import requests as cf_requests
except ImportError:
    print("ERROR: curl_cffi no instalado")
    sys.exit(1)

try:
    import browsercookie
    _BROWSERCOOKIE_AVAILABLE = True
except ImportError:
    _BROWSERCOOKIE_AVAILABLE = False
    print("⚠️  browser-cookie3 no instalado - sin cookies de Chrome")

from bs4 import BeautifulSoup

QUERY = "water"   # ← cambia aquí si quieres probar otra query
MAX   = 10

_HOST        = "https://www.elibrary.ru"
_HOME_URL    = f"{_HOST}/defaultx.asp"
_RESULTS_URL = f"{_HOST}/query_results.asp"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

session = cf_requests.Session(impersonate="chrome120")

# Inyectar cookies de Chrome (contienen la verificación del CAPTCHA)
if _BROWSERCOOKIE_AVAILABLE:
    try:
        jar = browsercookie.chrome(domain_name=".elibrary.ru")
        chrome_cookies = {c.name: c.value for c in jar}
        for name, value in chrome_cookies.items():
            session.cookies.set(name, value, domain="www.elibrary.ru")
        print(f"✅ {len(chrome_cookies)} cookies de Chrome inyectadas: {list(chrome_cookies.keys())}")
    except Exception as e:
        print(f"⚠️  No se pudieron leer cookies de Chrome: {e}")
else:
    print("⚠️  browser-cookie3 no disponible")

# ── PASO 1: GET home ──────────────────────────────────────────────────────────
print(f"\n[1] GET {_HOME_URL}")
r0 = session.get(_HOME_URL, headers=HEADERS, timeout=20)
print(f"    status={r0.status_code}  url_final={r0.url}")

if "page_captcha" in str(r0.url):
    print("    ⛔ CAPTCHA en home — activa VPN o espera")
    sys.exit(1)

# Extraer campos ocultos del formulario (ViewState, etc.)
soup0 = BeautifulSoup(r0.text, "html.parser")
hidden_fields = {}
for inp in soup0.find_all("input", type="hidden"):
    name = inp.get("name","")
    val  = inp.get("value","")
    if name:
        hidden_fields[name] = val
        print(f"    hidden: {name!r} = {val!r}")

# Acción del formulario
for form in soup0.find_all("form"):
    action = form.get("action","")
    method = form.get("method","?")
    print(f"    form action={action!r} method={method}")

time.sleep(1.0)

# ── PASO 2: POST a query_results.asp ─────────────────────────────────────────
headers_post = {**HEADERS,
    "Referer": _HOME_URL,
    "Origin": _HOST,
    "Content-Type": "application/x-www-form-urlencoded",
}

form_data = {
    **hidden_fields,        # incluir todos los campos ocultos
    "ftext": QUERY,
    "where_name": "on",
    "where_abstract": "on",
    "where_keywords": "on",
    "where_affiliation": "",
    "where_references": "",
    "type_article": "on",
    "search_morph": "on",
    "queryboxid": "",
    "itemboxid": "",
    "begin_year": "",
    "end_year": "",
    "issues": "all",
    "orderby": "rank",
    "order": "rev",
    "changed": "1",
}

print(f"\n[2] POST {_RESULTS_URL}  (query={QUERY!r})")
r1 = session.post(_RESULTS_URL, data=form_data, headers=headers_post, timeout=30)
print(f"    status={r1.status_code}  url_final={r1.url}")
print(f"    html_length={len(r1.text)}")

if "page_captcha" in str(r1.url):
    print("    ⛔ CAPTCHA tras POST")
    sys.exit(1)

# ── PASO 3: Analizar respuesta ────────────────────────────────────────────────
soup1 = BeautifulSoup(r1.text, "html.parser")
table = soup1.find("table", id="restab")
print(f"\n[3] tabla #restab: {'ENCONTRADA' if table else 'NO encontrada'}")

if not table:
    # Mostrar primeros 2000 chars para entender qué devolvió el servidor
    text_preview = soup1.get_text(separator="\n", strip=True)[:2000]
    print("    -- preview del body --")
    print(text_preview)
    print("    -- fin preview --")

    # Guardar HTML completo para inspección
    with open("debug_elibrary_response.html", "w", encoding="utf-8") as f:
        f.write(r1.text)
    print("\n  HTML guardado en debug_elibrary_response.html")
    sys.exit(1)

rows = table.find_all("tr")
print(f"    filas totales: {len(rows)}  (1 cabecera + {len(rows)-1} datos)")

count = 0
for row in rows[1:]:
    link = row.find("a", href=re.compile(r"/item\.asp"))
    if not link:
        continue
    count += 1
    href  = link.get("href","")
    title = link.get_text(strip=True)

    # Autores: buscar la <font color="#00008f"> que tiene <i> hijo
    # (la primera con ese color es el número de orden, no los autores)
    authors = ""
    for font_tag in row.find_all("font", color="#00008f"):
        italic = font_tag.find("i")
        if italic:
            authors = italic.get_text(separator=", ", strip=True)
            break

    year_m = re.search(r"\b(19|20)\d{2}\b", row.get_text())
    year   = year_m.group() if year_m else "?"

    print(f"\n  [{count}] {title[:70]}")
    print(f"       url    : {_HOST}{href}")
    print(f"       autores: {authors[:60]}")
    print(f"       año    : {year}")

    if count >= MAX:
        break

print(f"\n✅ Total artículos parseados: {count}")
