from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from .config import settings


log = logging.getLogger(__name__)

# Cache only a *successful* client. A failed init must not poison the whole
# process: lru_cache would have permanently cached None on a transient cold-start
# failure, silently disabling Firebase until restart.
_client_cache: Optional[Any] = None


def get_db() -> Optional[Any]:
    """
    Return a Firestore client when Firebase is configured.

    Firebase is an additive persistence layer. If credentials are missing or
    invalid, callers should silently fall back to local x-ray logs. Initialization
    is retried on each call until it succeeds, then the client is cached.
    """
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except Exception as exc:
        log.warning("Firebase Admin SDK is unavailable: %s", exc)
        return None

    try:
        if not firebase_admin._apps:
            project_id = settings.firebase_project_id or None
            raw_json = (settings.firebase_service_account_json or "").strip()
            credentials_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()

            if raw_json:
                info = json.loads(raw_json)
                cred = credentials.Certificate(info)
                firebase_admin.initialize_app(cred, {"projectId": project_id or info.get("project_id")})
            elif credentials_path:
                cred = credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(cred, {"projectId": project_id} if project_id else None)
            else:
                firebase_admin.initialize_app(options={"projectId": project_id} if project_id else None)

        _client_cache = firestore.client()
        log.info("[firebase] Firestore client initialized.")
        return _client_cache
    except Exception as exc:
        log.warning("Firebase/Firestore is not configured: %s", exc)
        return None

