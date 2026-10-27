"""Append audit entries for security-relevant meeting actions (SECURITY.md 3).

Called from inside the host-action transaction so the audit row commits with
the state change it describes; failures must never break the action itself.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AUDIT_ACTIONS, AuditLog

logger = logging.getLogger(__name__)


async def audit(
    session: AsyncSession,
    *,
    meeting_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    target_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Record one security-relevant action; unknown actions are logged loudly.

    Actions are developer-hardcoded strings, so an unknown value is a bug — but
    dropping the row would leave the audit trail silently incomplete. Record it
    anyway and shout, so a missing action name is never a quiet gap.
    """
    if action not in AUDIT_ACTIONS:
        logger.error("audit action %r is not in AUDIT_ACTIONS — recording anyway", action)
    session.add(
        AuditLog(
            meeting_id=meeting_id,
            actor_id=actor_id,
            action=action,
            target_id=target_id,
            detail=detail,
        )
    )
