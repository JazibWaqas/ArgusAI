from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Optional

from .config import settings


log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_db() -> Optional[Any]:
    """
    Return a Firestore client when Firebase is configured.

    Firebase is an additive persistence layer. If credentials are missing or
    invalid, callers should silently fall back to local x-ray logs.
    """
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

        return firestore.client()
    except Exception as exc:
        log.warning("Firebase/Firestore is not configured: %s", exc)
        return None

