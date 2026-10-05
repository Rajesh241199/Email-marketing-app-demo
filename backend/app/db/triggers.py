"""Database-level protection for opt-outs (BR-05, CMPY-03, SUB-05).

Application code (CSV import, API, automations) must already respect these rules. The
triggers below are the safety net so a bug or a raw UPDATE can never quietly re-subscribe
someone who opted out.

Rules enforced
--------------
subscribers
  * INSERT: if the email has an active row in ``suppressions`` for the account, the new
    subscriber is stored as ``suppressed`` whatever status the caller asked for.
  * UPDATE: ``unsubscribed``/``suppressed`` -> ``subscribed`` is rejected.

list_memberships
  * UPDATE: ``opted_out`` -> ``active`` is rejected.

Explicit re-subscription (the subscriber opts back in through the preference center, or a
confirmed double opt-in) is allowed by setting a transaction-local flag first::

    await session.execute(text("SET LOCAL app.allow_resubscribe = 'on'"))

The same code path must lift the matching ``suppressions`` row and write a
``subscription_events`` row with event_type = 'resubscribed'.

Alembic does not autogenerate triggers. The initial migration should run
``op.execute(sql)`` for each statement in ``TRIGGER_DDL`` (and ``DROP_DDL`` on downgrade).
"""

from sqlalchemy import DDL, Table, event

PROTECT_SUBSCRIBER_FN = """
CREATE OR REPLACE FUNCTION protect_subscriber_optout() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF EXISTS (
            SELECT 1 FROM suppressions s
            WHERE s.account_id = NEW.account_id
              AND s.email = NEW.email
              AND s.lifted_at IS NULL
        ) THEN
            NEW.status := 'suppressed';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status IN ('unsubscribed', 'suppressed')
       AND NEW.status = 'subscribed'
       AND COALESCE(current_setting('app.allow_resubscribe', true), '') <> 'on' THEN
        RAISE EXCEPTION 'subscriber % is %, re-subscription needs an explicit opt-in',
            OLD.id, OLD.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

PROTECT_SUBSCRIBER_TRIGGER = """
CREATE TRIGGER trg_subscribers_protect_optout
BEFORE INSERT OR UPDATE OF status ON subscribers
FOR EACH ROW EXECUTE FUNCTION protect_subscriber_optout();
"""

PROTECT_MEMBERSHIP_FN = """
CREATE OR REPLACE FUNCTION protect_membership_optout() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'opted_out'
       AND NEW.status = 'active'
       AND COALESCE(current_setting('app.allow_resubscribe', true), '') <> 'on' THEN
        RAISE EXCEPTION 'subscriber % opted out of list %, re-joining needs an explicit opt-in',
            OLD.subscriber_id, OLD.list_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

PROTECT_MEMBERSHIP_TRIGGER = """
CREATE TRIGGER trg_list_memberships_protect_optout
BEFORE UPDATE OF status ON list_memberships
FOR EACH ROW EXECUTE FUNCTION protect_membership_optout();
"""

TRIGGER_DDL: list[str] = [
    PROTECT_SUBSCRIBER_FN,
    PROTECT_SUBSCRIBER_TRIGGER,
    PROTECT_MEMBERSHIP_FN,
    PROTECT_MEMBERSHIP_TRIGGER,
]

DROP_DDL: list[str] = [
    "DROP TRIGGER IF EXISTS trg_list_memberships_protect_optout ON list_memberships;",
    "DROP FUNCTION IF EXISTS protect_membership_optout();",
    "DROP TRIGGER IF EXISTS trg_subscribers_protect_optout ON subscribers;",
    "DROP FUNCTION IF EXISTS protect_subscriber_optout();",
]


def register(subscribers: Table, list_memberships: Table) -> None:
    """Attach the triggers to ``metadata.create_all`` (used by tests)."""

    def ddl(sql: str) -> DDL:
        # DDL() applies %-formatting; escape the % placeholders used by RAISE.
        return DDL(sql.replace("%", "%%"))

    event.listen(subscribers, "after_create", ddl(PROTECT_SUBSCRIBER_FN))
    event.listen(subscribers, "after_create", ddl(PROTECT_SUBSCRIBER_TRIGGER))
    event.listen(list_memberships, "after_create", ddl(PROTECT_MEMBERSHIP_FN))
    event.listen(list_memberships, "after_create", ddl(PROTECT_MEMBERSHIP_TRIGGER))
