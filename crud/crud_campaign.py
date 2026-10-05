from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.campaign import Campaign, CampaignAudience, CampaignStatus
from schemas.campaign import CampaignCreate, CampaignUpdate


def get_campaign(db: Session, campaign_id: int) -> Optional[Campaign]:
    return db.query(Campaign).filter(Campaign.id == campaign_id).first()


def get_campaigns_by_account(db: Session, account_id: int) -> Sequence[Campaign]:
    return (
        db.query(Campaign)
        .filter(Campaign.account_id == account_id)
        .order_by(Campaign.created_at.desc())
        .all()
    )


def create_campaign(db: Session, account_id: int, data: CampaignCreate) -> Campaign:
    campaign = Campaign(
        account_id=account_id,
        name=data.name,
        sender_id=data.sender_id,
        template_id=data.template_id,
        subject=data.subject,
        pre_header=data.pre_header,
    )
    db.add(campaign)
    db.flush()
    for aud in (data.audiences or []):
        db.add(CampaignAudience(campaign_id=campaign.id, **aud.model_dump()))
    db.commit()
    db.refresh(campaign)
    return campaign


def update_campaign(db: Session, campaign_id: int, data: CampaignUpdate) -> Optional[Campaign]:
    campaign = get_campaign(db, campaign_id)
    if not campaign or campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.SCHEDULED):
        return None
    for key, value in data.model_dump(exclude_unset=True, exclude={"audiences"}).items():
        setattr(campaign, key, value)
    if data.audiences is not None:
        db.query(CampaignAudience).filter(CampaignAudience.campaign_id == campaign_id).delete()
        for aud in data.audiences:
            db.add(CampaignAudience(campaign_id=campaign_id, **aud.model_dump()))
    db.commit()
    db.refresh(campaign)
    return campaign


def delete_campaign(db: Session, campaign_id: int) -> bool:
    campaign = get_campaign(db, campaign_id)
    if not campaign:
        return False
    db.delete(campaign)
    db.commit()
    return True
