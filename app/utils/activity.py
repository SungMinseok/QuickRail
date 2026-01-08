from __future__ import annotations

import json
from typing import Any, Optional

from app import db
from app.models import ActivityLog


def log_activity_safe(
    *,
    user_id: int,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    project_id: Optional[int] = None,
    description: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    """
    기능 동작을 깨지 않도록, 예외 발생 시 조용히 무시하는 활동 로그 기록 함수.
    """
    try:
        meta_json = None
        if meta is not None:
            meta_json = json.dumps(meta, ensure_ascii=False)

        item = ActivityLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            description=description,
            meta_json=meta_json,
        )
        db.session.add(item)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


