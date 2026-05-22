"""Audit log and analytics event helpers."""
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .config import is_enabled
from .db import analytics_events, audit_log


async def log_event(
    action: str,
    actor_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    if not is_enabled("ENABLE_AUDIT_LOG"):
        return
    await audit_log.insert_one(
        {
            "id": str(uuid.uuid4()),
            "action": action,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip": ip,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def log_analytics(event_type: str, data: Optional[dict] = None) -> None:
    if not is_enabled("ENABLE_ANALYTICS_DASHBOARD"):
        return
    await analytics_events.insert_one(
        {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "data": data or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
