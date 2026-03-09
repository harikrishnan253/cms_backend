from sqlalchemy.orm import Session
from app.models import AuditLog

def log_action(db: Session, user_id: int, action: str, entity: str, entity_id: int):
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id
    )
    db.add(log)
    db.commit()
