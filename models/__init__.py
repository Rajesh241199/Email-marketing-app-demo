# Import all models so Base.metadata.create_all picks them up
from models.account import Account, User, UserAuth  # noqa: F401
from models.sender import SenderIdentity  # noqa: F401
from models.subscriber import (  # noqa: F401
    Subscriber, SubscriberList, Tag, CustomField,
    SubscriberListMembership, SubscriberTag, SubscriberCustomFieldValue
)
from models.import_job import ImportJob, ImportJobError  # noqa: F401
from models.template import Template  # noqa: F401
from models.campaign import Campaign, CampaignAudience, CampaignRecipient  # noqa: F401
from models.suppression import SuppressionList, UnsubscribeToken, PreferenceAuditLog  # noqa: F401
from models.automation import Automation, AutomationStep, AutomationEnrollment  # noqa: F401
