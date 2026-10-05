from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.deps import get_current_active_user
from crud import crud_campaign
from schemas.campaign import CampaignCreate, CampaignUpdate, CampaignOut

router = APIRouter()


@router.post("/", response_model=CampaignOut, status_code=201)
def create_campaign(account_id: int, data: CampaignCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_campaign.create_campaign(db, account_id, data)


@router.get("/", response_model=List[CampaignOut])
def list_campaigns(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_campaign.get_campaigns_by_account(db, account_id)


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    campaign = crud_campaign.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.put("/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: int, data: CampaignUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    campaign = crud_campaign.update_campaign(db, campaign_id, data)
    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found or is in an immutable state (sending/sent)"
        )
    return campaign


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_campaign.delete_campaign(db, campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found")


@router.post("/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    from models.campaign import CampaignStatus
    campaign = crud_campaign.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != CampaignStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Only scheduled campaigns can be cancelled")
    campaign.status = CampaignStatus.CANCELLED
    db.commit()
    return {"message": "Campaign cancelled"}
