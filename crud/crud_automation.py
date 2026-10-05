from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.automation import Automation, AutomationStep, AutomationStatus
from schemas.automation import AutomationCreate, AutomationUpdate


def get_automation(db: Session, automation_id: int) -> Optional[Automation]:
    return db.query(Automation).filter(Automation.id == automation_id).first()


def get_automations_by_account(db: Session, account_id: int) -> Sequence[Automation]:
    return db.query(Automation).filter(Automation.account_id == account_id).all()


def create_automation(db: Session, account_id: int, data: AutomationCreate) -> Automation:
    automation = Automation(
        account_id=account_id,
        name=data.name,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
    )
    db.add(automation)
    db.flush()
    for step in (data.steps or []):
        db.add(AutomationStep(automation_id=automation.id, **step.model_dump()))
    db.commit()
    db.refresh(automation)
    return automation


def update_automation(db: Session, automation_id: int, data: AutomationUpdate) -> Optional[Automation]:
    automation = get_automation(db, automation_id)
    if not automation:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(automation, key, value)
    db.commit()
    db.refresh(automation)
    return automation


def delete_automation(db: Session, automation_id: int) -> bool:
    automation = get_automation(db, automation_id)
    if not automation:
        return False
    db.delete(automation)
    db.commit()
    return True
