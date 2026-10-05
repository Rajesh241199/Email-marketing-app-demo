"""Import every model so Base.metadata is complete (used by Alembic's env.py).

    from app.db.models import Base
    target_metadata = Base.metadata
"""

from app.accounts.models import Account
from app.analytics.models import CampaignStats, EmailEvent, EmailMessage
from app.auth.models import AuthToken, User, UserIdentity, UserSession
from app.automations.models import Automation, AutomationEnrollment, AutomationStep
from app.campaigns.models import (
    Campaign,
    CampaignAudience,
    CampaignLink,
    CampaignRecipient,
    TestSend,
)
from app.db import triggers
from app.db.base import Base
from app.imports.models import ImportColumnMapping, ImportJob, ImportRowError
from app.preferences.models import SubscriptionEvent
from app.segments.models import Segment
from app.senders.models import Sender, SendingDomain
from app.subscribers.models import (
    CustomField,
    ListMembership,
    MailingList,
    Subscriber,
    SubscriberFieldValue,
    SubscriberTag,
    Tag,
)
from app.suppressions.models import Suppression
from app.templates.models import ContentBlock, MediaAsset, Template

__all__ = [
    "Base",
    "Account",
    "User",
    "AuthToken",
    "UserIdentity",
    "UserSession",
    "SendingDomain",
    "Sender",
    "Subscriber",
    "MailingList",
    "ListMembership",
    "Tag",
    "SubscriberTag",
    "CustomField",
    "SubscriberFieldValue",
    "Segment",
    "Suppression",
    "SubscriptionEvent",
    "ImportJob",
    "ImportColumnMapping",
    "ImportRowError",
    "ContentBlock",
    "Template",
    "MediaAsset",
    "Campaign",
    "CampaignAudience",
    "CampaignRecipient",
    "TestSend",
    "CampaignLink",
    "EmailMessage",
    "EmailEvent",
    "CampaignStats",
    "Automation",
    "AutomationStep",
    "AutomationEnrollment",
]

# Opt-out protection triggers (see app/db/triggers.py).
triggers.register(Subscriber.__table__, ListMembership.__table__)
