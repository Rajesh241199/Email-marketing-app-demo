"""Enums shared across several domains."""

import enum

from app.db.base import pg_enum


class ChangeSource(str, enum.Enum):
    """Where a subscriber / consent / suppression change came from."""

    MANUAL = "manual"
    CSV_IMPORT = "csv_import"
    API = "api"
    PREFERENCE_CENTER = "preference_center"
    ONE_CLICK_UNSUBSCRIBE = "one_click_unsubscribe"
    EMAIL_LINK = "email_link"
    PROVIDER_EVENT = "provider_event"
    AUTOMATION = "automation"


# Single shared SQLAlchemy type so the PostgreSQL enum is created once.
change_source_enum = pg_enum(ChangeSource, "change_source")


class EmailFrequency(str, enum.Enum):
    """Subscriber's frequency preference from the preference center (PREF-09)."""

    ALL = "all"  # every campaign they are eligible for
    WEEKLY_DIGEST = "weekly_digest"  # digest + essential campaigns only
    ESSENTIAL_ONLY = "essential_only"  # essential announcements only


class CampaignTier(str, enum.Enum):
    """What kind of send a campaign is, matched against EmailFrequency at freeze time."""

    REGULAR = "regular"
    DIGEST = "digest"
    ESSENTIAL = "essential"


# Which campaign tiers each frequency preference accepts.
FREQUENCY_ACCEPTS: dict[EmailFrequency, frozenset[CampaignTier]] = {
    EmailFrequency.ALL: frozenset(CampaignTier),
    EmailFrequency.WEEKLY_DIGEST: frozenset({CampaignTier.DIGEST, CampaignTier.ESSENTIAL}),
    EmailFrequency.ESSENTIAL_ONLY: frozenset({CampaignTier.ESSENTIAL}),
}

email_frequency_enum = pg_enum(EmailFrequency, "email_frequency")
campaign_tier_enum = pg_enum(CampaignTier, "campaign_tier")
