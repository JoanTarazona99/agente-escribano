"""Tests de los conectores de búsqueda."""
from unittest.mock import MagicMock, patch

import pytest
import respx
import httpx

from apps.search.connectors.arxiv import ArxivConnector
from apps.search.connectors.elibrary import ElibraryConnector
from apps.search.connectors.scopus import ScopusConnector
from apps.search.connectors.stubs import WOSConnector


ARXIV_SAMPLE_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</totalResults>
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Water Dissociation in Bipolar Membranes</title>
    <summary>This study investigates water dissociation phenomena in bipolar ion-exchange membranes under electric field conditions.</summary>
    <published>2023-01-15T00:00:00Z</published>
    <author><name>Ivanov, A.B.</name></author>
    <author><name>Petrov, C.D.</name></author>
    <link href="https://arxiv.org/abs/2301.00001v1" rel="alternate" type="text/html"/>
    <arxiv:doi>10.1234/example.doi</arxiv:doi>
    <category term="physics.chem-ph"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2302.00002v1</id>
    <title>Recombination Kinetics in Ion-Exchange Systems</title>
    <summary>A theoretical model for water recombination in electromembrane systems.</summary>
    <published>2023-02-20T00:00:00Z</published>
    <author><name>Sidorov, E.F.</name></author>
    <link href="https://arxiv.org/abs/2302.00002v1" rel="alternate" type="text/html"/>
    <category term="physics.chem-ph"/>
  </entry>
</feed>
"""


class TestArxivConnector:
    @respx.mock
    def test_search_returns_articles(self):
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=ARXIV_SAMPLE_ATOM)
        )
        connector = ArxivConnector()
        results = connector.search("water dissociation electromembrane")
        assert len(results) == 2
        assert results[0].title == "Water Dissociation in Bipolar Membranes"
        assert results[0].year == 2023
        assert results[0].doi == "10.1234/example.doi"
        assert results[0].source_db == "arxiv"
        assert "Ivanov" in results[0].authors

    @respx.mock
    def test_search_returns_empty_on_http_error(self):
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        connector = ArxivConnector()
        results = connector.search("test")
        assert results == []

    @respx.mock
    def test_source_db_is_arxiv(self):
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=ARXIV_SAMPLE_ATOM)
        )
        connector = ArxivConnector()
        results = connector.search("test")
        assert all(r.source_db == "arxiv" for r in results)

    def test_is_available_always_true(self):
        assert ArxivConnector().is_available() is True

    @respx.mock
    def test_retries_on_timeout(self):
        """Connector retries after timeout and succeeds on next attempt."""
        route = respx.get("https://export.arxiv.org/api/query")
        route.side_effect = [
            httpx.TimeoutException("connect timeout"),
            httpx.Response(200, text=ARXIV_SAMPLE_ATOM),
        ]
        connector = ArxivConnector()
        results = connector.search("test")
        assert len(results) == 2
        assert route.call_count == 2

    @respx.mock
    def test_retries_on_429(self):
        """Connector retries after 429 rate limit."""
        route = respx.get("https://export.arxiv.org/api/query")
        route.side_effect = [
            httpx.Response(429, text="Too Many Requests"),
            httpx.Response(200, text=ARXIV_SAMPLE_ATOM),
        ]
        connector = ArxivConnector()
        results = connector.search("test")
        assert len(results) == 2

    def test_is_available_always_true(self):
        assert ArxivConnector().is_available() is True


class TestScopusConnectorStub:
    def test_raises_error_without_key(self, settings):
        settings.SCOPUS_API_KEY = ""
        connector = ScopusConnector()
        with pytest.raises(ValueError, match="SCOPUS_API_KEY"):
            connector.search("test")

    def test_is_available_false_without_key(self, settings):
        settings.SCOPUS_API_KEY = ""
        assert ScopusConnector().is_available() is False

    def test_is_available_true_with_key(self, settings):
        settings.SCOPUS_API_KEY = "fake-key-12345"
        assert ScopusConnector().is_available() is True

    @respx.mock
    def test_search_returns_articles(self, settings):
        """Test Scopus search with mocked API response."""
        settings.SCOPUS_API_KEY = "fake-key-12345"
        
        # Mock Scopus API response
        mock_response = {
            "search-results": {
                "entry": [
                    {
                        "eid": "123456789",
                        "dc:title": "Water Dissociation in Bipolar Membranes",
                        "dc:creator": "Smith, John; Doe, Jane",
                        "dc:description": "Study of water dissociation mechanisms in electromembrane systems.",
                        "prism:coverDate": "2023-06-15",
                        "prism:doi": "10.1234/example.2023",
                        "prism:publicationName": "Journal of Membrane Science",
                        "link": [{"@ref": "scopus", "@href": "https://www.scopus.com/record/display.uri?eid=123456789"}],
                    },
                    {
                        "eid": "987654321",
                        "dc:title": "Ion Transport in Electrochemical Cells",
                        "dc:creator": "Brown, Mark",
                        "dc:description": "Analysis of ion transport phenomena.",
                        "prism:coverDate": "2022-03-20",
                        "prism:doi": "10.5678/example.2022",
                        "prism:publicationName": "Electrochimica Acta",
                        "link": [],
                    },
                ]
            }
        }
        
        respx.get("https://api.elsevier.com/content/search/scopus").mock(
            return_value=httpx.Response(200, json=mock_response, headers={"content-type": "application/json"})
        )
        
        connector = ScopusConnector()
        results = connector.search("water electrolysis")
        
        assert len(results) == 2
        assert results[0].title == "Water Dissociation in Bipolar Membranes"
        assert results[0].source_db == "scopus"
        assert results[0].source_id == "123456789"
        assert results[0].year == 2023
        assert results[0].doi == "10.1234/example.2023"
        assert results[0].journal == "Journal of Membrane Science"
        assert "Smith" in results[0].authors
        
        assert results[1].title == "Ion Transport in Electrochemical Cells"
        assert results[1].year == 2022


class TestWOSConnectorStub:
    def test_raises_not_implemented_without_key(self, settings):
        settings.WOS_API_KEY = ""
        connector = WOSConnector()
        with pytest.raises(NotImplementedError, match="WOS_API_KEY"):
            connector.search("test")


# ─── HTML de muestra para eLIBRARY ───────────────────────────────────────────
# Estructura real: href="/item.asp?id=...", autores en <font color="#00008f"><i>

_ELIBRARY_RESULTS_HTML = """
<html><body>
<table id="restab">
  <tr><th>Название</th><th>Авторы</th><th>Год</th></tr>
  <tr bgcolor="#f5f5f5" id="a12345">
    <td><div id="pdf_12345"></div></td>
    <td>
      <a href="/item.asp?id=12345"><b>Диссоциация воды в биполярных мембранах</b></a><br/>
      <font color="#00008f"><i>Иванов А.Б., Петров В.Г.</i></font><br/>
      <font color="#00008f">
        <a href="/contents.asp?id=99001">Электрохимия</a>. 2022.
      </font>
    </td>
    <td>0</td>
  </tr>
  <tr bgcolor="#f5f5f5" id="a67890">
    <td><div id="pdf_67890"></div></td>
    <td>
      <a href="/item.asp?id=67890"><b>Перенос ионов в электромембранных системах</b></a><br/>
      <font color="#00008f"><i>Сидоров Д.Е.</i></font><br/>
      <font color="#00008f">
        <a href="/contents.asp?id=99002">Журнал физической химии</a>. 2021.
      </font>
    </td>
    <td>0</td>
  </tr>
</table>
</body></html>
"""

_ELIBRARY_CAPTCHA_URL = "https://www.elibrary.ru/page_captcha.asp?rpage=..."


def _make_mock_response(text="", url="https://www.elibrary.ru/query_results.asp"):
    """Crea un mock de respuesta curl_cffi."""
    r = MagicMock()
    r.text = text
    r.url = url
    return r


class TestElibraryConnector:
    """Tests del conector eLIBRARY con curl_cffi mockeado."""

    def _make_session(self, home_url=None, post_url=None, post_html=""):
        """
        Devuelve Session mock con el flujo real:
          session.get(home)  → sin captcha
          session.post(query_results) → HTML con resultados
        """
        session = MagicMock()
        session.get.return_value = _make_mock_response(
            url=home_url or "https://www.elibrary.ru/defaultx.asp"
        )
        session.post.return_value = _make_mock_response(
            text=post_html,
            url=post_url or "https://www.elibrary.ru/query_results.asp",
        )
        return session

    @patch("apps.search.connectors.elibrary._CURL_CFFI_AVAILABLE", False)
    def test_returns_empty_when_curl_cffi_missing(self):
        results = ElibraryConnector().search("тест")
        assert results == []

    @patch("apps.search.connectors.elibrary.cf_requests")
    def test_returns_empty_on_captcha_at_home(self, mock_cf):
        session = MagicMock()
        session.get.return_value = _make_mock_response(url=_ELIBRARY_CAPTCHA_URL)
        mock_cf.Session.return_value = session

        results = ElibraryConnector().search("тест")
        assert results == []

    @patch("apps.search.connectors.elibrary.cf_requests")
    def test_returns_empty_on_captcha_after_post(self, mock_cf):
        session = self._make_session(post_url=_ELIBRARY_CAPTCHA_URL, post_html="")
        mock_cf.Session.return_value = session

        results = ElibraryConnector().search("тест")
        assert results == []

    @patch("apps.search.connectors.elibrary.cf_requests")
    def test_returns_articles_with_valid_response(self, mock_cf):
        session = self._make_session(post_html=_ELIBRARY_RESULTS_HTML)
        mock_cf.Session.return_value = session

        results = ElibraryConnector().search("диссоциация")
        assert len(results) == 2
        assert results[0].title == "Диссоциация воды в биполярных мембранах"
        assert results[0].source_db == "elibrary"
        assert results[0].source_id == "12345"
        assert results[0].year == 2022
        assert "Иванов" in results[0].authors
        assert results[0].url == "https://www.elibrary.ru/item.asp?id=12345"
        assert results[0].journal == "Электрохимия"

    @patch("apps.search.connectors.elibrary.cf_requests")
    def test_respects_max_results(self, mock_cf):
        session = self._make_session(post_html=_ELIBRARY_RESULTS_HTML)
        mock_cf.Session.return_value = session

        results = ElibraryConnector().search("тест", max_results=1)
        assert len(results) == 1

    @patch("apps.search.connectors.elibrary.cf_requests")
    def test_returns_empty_when_no_table(self, mock_cf):
        session = self._make_session(post_html="<html><body>Sin resultados</body></html>")
        mock_cf.Session.return_value = session

        results = ElibraryConnector().search("тест")
        assert results == []

    @patch("apps.search.connectors.elibrary.cf_requests")
    def test_returns_empty_on_unexpected_exception(self, mock_cf):
        session = MagicMock()
        session.get.side_effect = Exception("error de red")
        mock_cf.Session.return_value = session

        results = ElibraryConnector().search("тест")
        assert results == []
