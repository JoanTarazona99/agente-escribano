"""
Stubs para Web of Science.
Se activará cuando el usuario proporcione la API key correspondiente.
"""
from __future__ import annotations

from django.conf import settings

from .base import ArticleData, BaseSearchConnector


class WOSConnector(BaseSearchConnector):
    """
    Conector para Web of Science (Clarivate API).
    Requiere WOS_API_KEY en settings / .env.

    Documentación API: https://developer.clarivate.com/apis/wos
    """

    SOURCE_DB = "wos"

    def is_available(self) -> bool:
        return bool(getattr(settings, "WOS_API_KEY", ""))

    def search(self, query: str, max_results: int = 50) -> list[ArticleData]:
        api_key = getattr(settings, "WOS_API_KEY", "")
        if not api_key:
            raise NotImplementedError(
                "WOSConnector requiere WOS_API_KEY configurada en .env. "
                "Consulta https://developer.clarivate.com/ para obtener credenciales."
            )
        # TODO: implementar cuando se tenga API key
        # POST https://wos-api.clarivate.com/api/wos
        #   headers: {"X-ApiKey": api_key}
        raise NotImplementedError("Implementación pendiente de credenciales Web of Science.")

