"""موصلات مصادر البيانات الحية."""
from .base import (
    ConnectorResult, FailureKind, clear_cache, close_clients, fetch, http_get,
)
from .registry import CONNECTORS, coverage, gather_context, probe_sources

__all__ = [
    "ConnectorResult", "FailureKind", "fetch", "http_get",
    "clear_cache", "close_clients",
    "CONNECTORS", "coverage", "gather_context", "probe_sources",
]
