"""Paquete de conectores de búsqueda."""
from .arxiv import ArxivConnector
from .base import ArticleData, BaseSearchConnector
from .elibrary import ElibraryConnector
from .scopus import ScopusConnector
from .stubs import WOSConnector

__all__ = [
    "ArticleData",
    "BaseSearchConnector",
    "ArxivConnector",
    "ElibraryConnector",
    "ScopusConnector",
    "WOSConnector",
]
