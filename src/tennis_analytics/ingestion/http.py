"""Accès HTTP minimal (urllib) avec tentatives — échecs explicites."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Final

from loguru import logger

#: User-Agent générique : aucune donnée personnelle n'est transmise aux sources.
USER_AGENT: Final[str] = "tennis-analytics-ingestion/0.2"


class SourceUnavailableError(RuntimeError):
    """Une source distante n'a pas pu être lue (après toutes les tentatives)."""


def fetch_bytes(url: str, *, timeout_s: int = 60, attempts: int = 3) -> bytes:
    """Télécharge une ressource et retourne son contenu brut.

    Args:
        url: URL complète.
        timeout_s: Délai maximal par tentative.
        attempts: Nombre de tentatives (backoff linéaire).

    Returns:
        Contenu de la réponse.

    Raises:
        SourceUnavailableError: Si toutes les tentatives échouent (y compris 404).
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                break
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
        logger.warning(
            "Échec de lecture (tentative {}/{}) : {} — {}", attempt, attempts, url, last_error
        )
        time.sleep(1.5 * attempt)
    raise SourceUnavailableError(f"Source injoignable : {url} ({last_error})")
