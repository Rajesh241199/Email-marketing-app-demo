"""Audience resolution + the 4-part eligibility check from docs/architecture/schema-v1.md
section 4. This is the one piece of send-pipeline logic built in the CRUD bootstrap pass -
everything downstream of a frozen `campaign_recipients` row (actual provider dispatch) is
deferred (see campaigns/router.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.campaigns.models import (
    AudienceMode,
    Campaign,
    CampaignAudience,
    CampaignRecipient,
    RecipientStatus,
    SkipReason,
)
from app.db.enums import FREQUENCY_ACCEPTS
from app.subscribers.models import ListMembership, MembershipStatus, Subscriber, SubscriberTag
from app.suppressions.models import Suppression


def _resolve_audience_targets(
    db: Session, account_id: uuid.UUID, audience: CampaignAudience
) -> list[Subscriber]:
    if audience.list_id is not None:
        return (
            db.query(Subscriber)
            .join(ListMembership, ListMembership.subscriber_id == Subscriber.id)
            .filter(
                Subscriber.account_id == account_id,
                ListMembership.list_id == audience.list_id,
                ListMembership.status == MembershipStatus.ACTIVE,
            )
            .all()
        )
    if audience.tag_id is not None:
        return (
            db.query(Subscriber)
            .join(SubscriberTag, SubscriberTag.subscriber_id == Subscriber.id)
            .filter(Subscriber.account_id == account_id, SubscriberTag.tag_id == audience.tag_id)
            .all()
        )
    if audience.subscriber_id is not None:
        subscriber = db.get(Subscriber, audience.subscriber_id)
        if subscriber is None or subscriber.account_id != account_id:
            return []
        return [subscriber]
    if audience.segment_id is not None:
        # Segments domain is built independently; import lazily so this module doesn't hard-fail
        # to import before that lands, and so campaigns has no load-time coupling to it.
        from app.segments.evaluator import resolve_segment_subscriber_ids
        from app.segments.models import Segment

        segment = db.get(Segment, audience.segment_id)
        if segment is None or segment.account_id != account_id:
            return []
        subscriber_ids = resolve_segment_subscriber_ids(db, segment)
        if not subscriber_ids:
            return []
        return db.query(Subscriber).filter(Subscriber.id.in_(subscriber_ids)).all()
    return []


def resolve_audience_matches(
    db: Session, campaign: Campaign
) -> dict[str, tuple[uuid.UUID, str, uuid.UUID]]:
    """email (lowercased) -> (subscriber_id, email, matched_audience_id).

    Union of INCLUDE rules, minus the union of EXCLUDE rules. The first INCLUDE rule to
    match a given email wins `matched_audience_id` (CMP-04's documented behavior).
    """
    audiences = (
        db.query(CampaignAudience).filter(CampaignAudience.campaign_id == campaign.id).all()
    )
    includes = [a for a in audiences if a.mode == AudienceMode.INCLUDE]
    excludes = [a for a in audiences if a.mode == AudienceMode.EXCLUDE]

    included: dict[str, tuple[uuid.UUID, str, uuid.UUID]] = {}
    for audience in includes:
        for subscriber in _resolve_audience_targets(db, campaign.account_id, audience):
            key = subscriber.email.lower()
            if key not in included:
                included[key] = (subscriber.id, subscriber.email, audience.id)

    excluded_keys: set[str] = set()
    for audience in excludes:
        for subscriber in _resolve_audience_targets(db, campaign.account_id, audience):
            excluded_keys.add(subscriber.email.lower())

    return {k: v for k, v in included.items() if k not in excluded_keys}


def check_eligibility(db: Session, campaign: Campaign, subscriber: Subscriber) -> SkipReason | None:
    active_suppression = (
        db.query(Suppression)
        .filter(
            Suppression.account_id == campaign.account_id,
            Suppression.email == subscriber.email,
            Suppression.lifted_at.is_(None),
        )
        .first()
    )
    if active_suppression is not None:
        return SkipReason.SUPPRESSED

    if subscriber.status.value == "unsubscribed":
        return SkipReason.UNSUBSCRIBED
    if subscriber.status.value == "suppressed":
        return SkipReason.SUPPRESSED

    if campaign.topic_list_id is not None:
        membership = (
            db.query(ListMembership)
            .filter(
                ListMembership.list_id == campaign.topic_list_id,
                ListMembership.subscriber_id == subscriber.id,
            )
            .first()
        )
        if membership is None or membership.status != MembershipStatus.ACTIVE:
            return SkipReason.LIST_OPTED_OUT

    accepted_tiers = FREQUENCY_ACCEPTS[subscriber.email_frequency]
    if campaign.tier not in accepted_tiers:
        return SkipReason.FREQUENCY_PREFERENCE

    return None


def freeze_campaign(db: Session, campaign: Campaign) -> tuple[int, int]:
    """Write `campaign_recipients`, set `audience_frozen_at`/`eligible_count`.

    Returns (eligible_count, skipped_count). Caller is responsible for the surrounding
    validation (confirmed_at set, not already frozen) and for committing.
    """
    matches = resolve_audience_matches(db, campaign)
    eligible_count = 0
    skipped_count = 0
    for subscriber_id, email, matched_audience_id in matches.values():
        subscriber = db.get(Subscriber, subscriber_id)
        reason = (
            check_eligibility(db, campaign, subscriber) if subscriber else SkipReason.INVALID_EMAIL
        )
        status = RecipientStatus.SKIPPED if reason else RecipientStatus.PENDING
        db.add(
            CampaignRecipient(
                campaign_id=campaign.id,
                subscriber_id=subscriber_id,
                email=email,
                matched_audience_id=matched_audience_id,
                status=status,
                skip_reason=reason,
            )
        )
        if reason is None:
            eligible_count += 1
        else:
            skipped_count += 1

    campaign.audience_frozen_at = datetime.now(UTC)
    campaign.eligible_count = eligible_count
    db.flush()
    return eligible_count, skipped_count
