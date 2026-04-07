"""
Conector para eLIBRARY.ru - scraping con curl_cffi (impersona Chrome 120).

CAPTCHA: eLIBRARY lo lanza cuando el servidor no reconoce la sesion.
  La sesion se identifica por cookies (no solo por IP). Solucion:
    1. Persistir cookies en disco entre ejecuciones (_COOKIE_FILE).
    2. Si se detecta CAPTCHA, abrir la URL en el navegador del sistema
       y reintentar hasta _CAPTCHA_RETRIES veces.
Flujo:
    1. GET www.elibrary.ru/defaultx.asp  - obtener cookies + campos ocultos
    2. POST www.elibrary.ru/query_results.asp  - accion real del formulario
    3. Parsear table#restab en la respuesta directa del POST.
"""
from __future__ import annotations

import json
import re
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cf_requests
    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False

try:
    import browser_cookie3 as browsercookie  # browser-cookie3 package
    _BROWSERCOOKIE_AVAILABLE = True
except ImportError:
    _BROWSERCOOKIE_AVAILABLE = False

from django.conf import settings

from .base import ArticleData, BaseSearchConnector

_ELIBRARY_HOST  = "https://www.elibrary.ru"
_HOME_URL       = f"{_ELIBRARY_HOST}/defaultx.asp"
_RESULTS_URL    = f"{_ELIBRARY_HOST}/query_results.asp"
_CAPTCHA_MARKER = "page_captcha.asp"

_COOKIE_FILE      = Path(settings.BASE_DIR) / ".elibrary_cookies.json"
_CAPTCHA_WAIT_SECS = 30   # cuánto esperar tras abrir el navegador
_CAPTCHA_RETRIES   = 3    # reintentos DESPUÉS de la espera (sin abrir navegador de nuevo)


class ElibraryConnector(BaseSearchConnector):

    SOURCE_DB = "elibrary"

    _BASE_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "max-age=0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        if not _CURL_CFFI_AVAILABLE:
            self.logger.error("curl_cffi no instalado. Ejecute: pip install curl-cffi")
            return []
        self.logger.info("eLIBRARY search: %r (max=%d)", query, max_results)
        try:
            return self._do_search(query, max_results)
        except Exception as exc:
            self.logger.error("eLIBRARY error inesperado: %s", exc, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Cookies persistentes
    # ------------------------------------------------------------------

    def _load_cookies(self) -> dict:
        """Intenta cargar cookies en este orden:
        0. Variable de entorno ELIBRARY_COOKIES_JSON (para Render/Prod)
        1. Chrome/Edge instalado (browser-cookie3) — local
        2. Archivo en disco _COOKIE_FILE — sesión previa
        """
        # 0. Producción: leer desde variable de entorno (inyectada por Render)
        import os
        env_cookies = os.getenv("ELIBRARY_COOKIES_JSON")
        if env_cookies:
            try:
                data = json.loads(env_cookies)
                self.logger.debug("eLIBRARY: %d cookies desde variable de entorno", len(data))
                return data
            except Exception as exc:
                self.logger.warning("eLIBRARY: error parseando ELIBRARY_COOKIES_JSON: %s", exc)

        # 1. Leer cookies directamente de Chrome/Edge (Local con GUI)
        if _BROWSERCOOKIE_AVAILABLE:
            try:
                jar = browsercookie.chrome(domain_name=".elibrary.ru")
                chrome_cookies = {c.name: c.value for c in jar}
                if chrome_cookies:
                    self.logger.debug(
                        "eLIBRARY: %d cookies leídas de Chrome", len(chrome_cookies)
                    )
                    return chrome_cookies
            except Exception as exc:
                self.logger.debug("eLIBRARY: no se pudo leer cookies de Chrome: %s", exc)

        # 2. Fallback: archivo guardado por el propio conector
        try:
            if _COOKIE_FILE.exists():
                data = json.loads(_COOKIE_FILE.read_text(encoding="utf-8"))
                self.logger.debug("eLIBRARY: %d cookies cargadas de disco", len(data))
                return data
        except Exception as exc:
            self.logger.warning("eLIBRARY: error leyendo cookies de disco: %s", exc)
        return {}

    def _save_cookies(self, session) -> None:
        try:
            cookies = dict(session.cookies)
            _COOKIE_FILE.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.logger.debug("eLIBRARY: %d cookies guardadas en disco", len(cookies))
        except Exception as exc:
            self.logger.warning("eLIBRARY: error guardando cookies: %s", exc)

    def _clear_cookies(self) -> None:
        try:
            if _COOKIE_FILE.exists():
                _COOKIE_FILE.unlink()
                self.logger.info("eLIBRARY: cookies eliminadas (sesion expirada)")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Busqueda
    # ------------------------------------------------------------------

    def _make_session(self, proxy_url: str, use_cookies: bool = False) -> object:
        """Crea una sesion curl_cffi, inyectando cookies de Chrome solo si se pide."""
        session = cf_requests.Session(impersonate="chrome120")
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        if use_cookies:
            for name, value in self._load_cookies().items():
                # Inyectar en ambos dominios para evitar bucles de redireccion
                session.cookies.set(name, value, domain="www.elibrary.ru")
                session.cookies.set(name, value, domain="elibrary.ru")
        return session

    def _do_search(self, query: str, max_results: int) -> list[ArticleData]:
        headers   = dict(self._BASE_HEADERS)
        proxy_url = getattr(settings, "ELIBRARY_PROXY_URL", "")
        browser_opened = False  # el navegador se abre como máximo UNA vez

        # Intento 0: sesion limpia (sin cookies) - evita TooManyRedirects
        # Intentos 1+: con cookies de Chrome/disco - tras detectar CAPTCHA
        for attempt in range(_CAPTCHA_RETRIES + 1):
            use_cookies = attempt > 0
            session = self._make_session(proxy_url, use_cookies=use_cookies)

            # PASO 1: GET home
            try:
                r0 = session.get(_HOME_URL, headers=headers, timeout=20)
            except Exception as exc:
                self.logger.warning(
                    "eLIBRARY: error en GET home (intento %d): %s - reintentando sin cookies",
                    attempt, exc,
                )
                self._clear_cookies()
                time.sleep(2)
                continue

            # Comprobar CAPTCHA ya en el GET home
            if _CAPTCHA_MARKER in str(r0.url):
                if attempt >= _CAPTCHA_RETRIES:
                    self.logger.error(
                        "eLIBRARY: CAPTCHA en GET home no resuelto tras %d intentos.",
                        _CAPTCHA_RETRIES,
                    )
                    return []
                if not browser_opened:
                    self.logger.warning(
                        "eLIBRARY CAPTCHA en GET home — abriendo navegador una sola vez. "
                        "Resuelve el CAPTCHA y espera %ds...",
                        _CAPTCHA_WAIT_SECS,
                    )
                    webbrowser.open(str(r0.url))
                    browser_opened = True
                    time.sleep(_CAPTCHA_WAIT_SECS)
                else:
                    self.logger.warning(
                        "eLIBRARY: CAPTCHA aún activo (intento %d/%d), reintentando en 5s...",
                        attempt + 1, _CAPTCHA_RETRIES,
                    )
                    time.sleep(5)
                continue

            time.sleep(1.0)

            # Extraer campos ocultos del formulario
            soup0 = BeautifulSoup(r0.text, "html.parser")
            hidden_fields: dict[str, str] = {
                inp["name"]: inp.get("value", "")
                for inp in soup0.find_all("input", type="hidden")
                if inp.get("name")
            }
            self.logger.debug("eLIBRARY: %d campos ocultos del home", len(hidden_fields))

            # PASO 2: POST a query_results.asp
            headers_post = {
                **headers,
                "Referer": _HOME_URL,
                "Origin": _ELIBRARY_HOST,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            # eLibrary requiere campos específicos para que el POST no devuelva 
            # solo el formulario vacío o "No se encontraron publicaciones".
            form_data = {
                **hidden_fields,
                "ftext": query,
                "where_name": "on",
                "where_abstract": "on",
                "where_keywords": "on",
                "type_article": "on",
                "search_morph": "on",
                "issues": "all",
                "orderby": "rank",
                "order": "rev",
                "changed": "1",
            }

            r1 = session.post(_RESULTS_URL, data=form_data, headers=headers_post, timeout=30)

            # Debug temporal para producción (Render) para verificar qué devuelve eLibrary
            if not r1.text.count("restab"):
                self.logger.warning(
                    "eLIBRARY DEBUG: status=%d url=%s preview=%r",
                    r1.status_code, str(r1.url), r1.text[:500]
                )

            if _CAPTCHA_MARKER in str(r1.url):
                if attempt >= _CAPTCHA_RETRIES:
                    self.logger.error(
                        "eLIBRARY: CAPTCHA en POST no resuelto tras %d intentos.",
                        _CAPTCHA_RETRIES,
                    )
                    return []
                if not browser_opened:
                    self.logger.warning(
                        "eLIBRARY CAPTCHA en POST — abriendo navegador una sola vez. "
                        "Resuelve el CAPTCHA y espera %ds...",
                        _CAPTCHA_WAIT_SECS,
                    )
                    webbrowser.open(str(r1.url))
                    browser_opened = True
                    time.sleep(_CAPTCHA_WAIT_SECS)
                else:
                    self.logger.warning(
                        "eLIBRARY: CAPTCHA aún activo en POST (intento %d/%d), reintentando en 5s...",
                        attempt + 1, _CAPTCHA_RETRIES,
                    )
                    time.sleep(5)
                continue

            parsed = urlparse(str(r1.url))
            final_host = f"{parsed.scheme}://{parsed.netloc}"
            return self._parse_results(r1.text, max_results, final_host)

        self.logger.error("eLIBRARY: todos los reintentos de CAPTCHA agotados.")
        return []

    # ------------------------------------------------------------------
    # Parser HTML
    # ------------------------------------------------------------------

    def _parse_results(
        self,
        html: str,
        max_results: int,
        host: str = "https://www.elibrary.ru",
    ) -> list[ArticleData]:
        soup  = BeautifulSoup(html, "html.parser")
        table = soup.find("table", id="restab")
        if not table:
            self.logger.warning("eLIBRARY: tabla #restab no encontrada.")
            return []

        articles: list[ArticleData] = []
        for row in table.find_all("tr")[1:]:
            title_link = row.find("a", href=re.compile(r"/item\.asp"))
            if not title_link:
                continue
            title = title_link.get_text(strip=True)
            if not title:
                continue

            href = title_link.get("href", "")
            article_url = f"{host}{href}" if href.startswith("/") else href

            source_id = ""
            m = re.search(r"id=(\d+)", href)
            if m:
                source_id = m.group(1)

            # Autores: la 1a <font color="#00008f"> es el numero de orden (sin <i>);
            # los autores estan en la primera que SI tiene <i> hijo.
            authors = ""
            for font_tag in row.find_all("font", color="#00008f"):
                italic = font_tag.find("i")
                if italic:
                    authors = italic.get_text(separator=", ", strip=True)
                    break

            journal = ""
            jlinks = row.find_all("a", href=re.compile(r"contents\.asp"))
            if jlinks:
                journal = jlinks[0].get_text(strip=True)

            year: int | None = None
            ym = re.search(r"\b(19|20)\d{2}\b", row.get_text())
            if ym:
                year = int(ym.group())

            articles.append(ArticleData(
                title=title,
                authors=authors,
                year=year,
                url=article_url,
                source_db=self.SOURCE_DB,
                source_id=source_id,
                journal=journal,
                language="ru",
            ))
            if len(articles) >= max_results:
                break

        self.logger.info("eLIBRARY: %d articulos recuperados", len(articles))
        return articles
