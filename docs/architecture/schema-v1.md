# Schema V1 — design notes

The SQLAlchemy models in `backend/app/*/models.py` are the source of truth.
`docs/architecture/schema.dbml` is generated from them (`python -m scripts.export_dbml`)
for dbdiagram.io. Database-level opt-out protection lives in `backend/app/db/triggers.py`.

**Size:** 34 tables · 30 enums · 16 check constraints · 2 triggers.
**Verified** against PostgreSQL 16: every rule below was exercised with real inserts and
updates (41/41 checks passed), and the hot query paths were confirmed to use their indexes.

---

## 1. Changes from the draft schema

| Area | Change |
|---|---|
| Auth | Added `user_identities` (external IdP issuer + subject) and `user_sessions` (revocable refresh tokens). `users.password_hash` stays nullable. |
| Frozen audience | Added `campaign_recipients`. `email_messages` now links 1:1 to a recipient row. |
| Preferences | Added `subscribers.email_frequency` and `campaigns.tier` (PREF-09). |
| Templates | Added `content_blocks` (reusable header/footer); `templates.header_block_id` / `footer_block_id`. |
| Opt-out safety | Triggers stop any code path from re-subscribing an opted-out contact. |
| Message states | `sent` split into `submitting` → `accepted` → `delivered`; added `rejected`, `cancelled`. |
| Events | `email_events` is the source of truth; unique `(provider, provider_event_id)`. |
| Stats | `campaign_stats` is explicitly derived (`last_event_id` watermark, `computed_at`). |
| Tracing | `correlation_id` on `import_jobs`, `campaigns`, `email_messages`, `email_events`, `subscription_events`. |
| Integrity | Check constraints on every multi-reference table; worker and FK indexes added. |
| Topic opt-outs | Added nullable `campaigns.topic_list_id` so segment/tag/subscriber-audience campaigns can also be tied to a preference-center topic (section 10 decision). |

---

## 2. Authentication (decision still open)

The schema supports all three options, so the V1 decision does not block migrations:

| Strategy | `users.password_hash` | `user_identities` | `user_sessions` / `auth_tokens` |
|---|---|---|---|
| Local email + password | set | — | used |
| Auth0 / Cognito / generic OIDC only | NULL | one row: `issuer` + `external_subject` (`sub` claim) | optional (IdP owns sessions) |
| Password now, Google/Microsoft later | set | added later per user | used |

A separate identities table is used instead of `auth_provider` / `external_subject` columns
on `users` so one person can link more than one login method, and the subject is unique
per issuer (`uq_user_identities_issuer_subject`).

**To decide:** which IdP (if any). If it is a hosted IdP only, `password_hash`,
`auth_tokens` and possibly `user_sessions` can be dropped before V1 is frozen.

---

## 3. Uniqueness

| Rule | Enforced by |
|---|---|
| Subscriber email unique **per account**, not globally, case-insensitive | `UNIQUE (account_id, email)` on `subscribers`, `email` is `citext` |
| User login email unique globally | `users.email UNIQUE` |
| One active suppression per email per account | partial unique `(account_id, email) WHERE lifted_at IS NULL` |
| One frozen recipient per email per campaign | `UNIQUE (campaign_id, email)` on `campaign_recipients` |
| One message per recipient (no double send on retry) | partial unique `email_messages(campaign_recipient_id)` |
| One message per automation step per enrollment | partial unique `(enrollment_id, automation_step_id)` |
| Provider message ID unique per provider | partial unique `(provider, provider_message_id)` |
| Each provider event stored once | `UNIQUE (provider, provider_event_id)` on `email_events` |

---

## 4. Preference center: how consent is represented

Four pieces of state, from strongest to weakest:

| Layer | Column / table | Set by | Meaning |
|---|---|---|---|
| 1. Suppression | `suppressions` (active = `lifted_at IS NULL`) | unsubscribe-all, hard bounce, complaint, manual block | **Never email this address from this account.** Keyed by email so it survives subscriber deletion and re-import. |
| 2. Global consent | `subscribers.status` | preference center, one-click unsubscribe, bounce/complaint processor | `subscribed` / `unsubscribed` / `suppressed`. Kept in sync with layer 1. |
| 3. Topic opt-down | `list_memberships.status` for lists with `show_in_preferences = true` | preference center | `opted_out` removes the person from that topic only (PREF-04). |
| 4. Frequency | `subscribers.email_frequency` vs `campaigns.tier` | preference center | `all` → every tier; `weekly_digest` → `digest` + `essential`; `essential_only` → `essential`. |

Every change is also appended to `subscription_events` (who, what, source, IP, user agent,
campaign/message that carried the link) — the audit trail for PREF-07 / CMPY-07.

### What each preference-center action writes

| Action | `suppressions` | `subscribers.status` | `list_memberships` | `subscription_events` |
|---|---|---|---|---|
| Opt out of one topic | — | unchanged | that list → `opted_out` | `list_opt_out` |
| Opt back in to a topic | — | unchanged | → `active` (explicit opt-in flag) | `list_opt_in` |
| Change frequency | — | unchanged | — | `profile_updated` |
| Unsubscribe from all / one-click (RFC 8058) | insert `reason = unsubscribe` | → `unsubscribed` | unchanged (history kept) | `unsubscribed` |
| Hard bounce / complaint | insert `hard_bounce` / `complaint` | → `suppressed` | unchanged | `suppressed` |
| Re-subscribe (explicit opt-in only) | set `lifted_at` | → `subscribed` (explicit opt-in flag) | unchanged | `resubscribed` |

### Eligibility rule (one function, used by campaigns and automations)

A subscriber is eligible for a send when **all** of these are true:

1. No active row in `suppressions` for `(account_id, email)`.
2. `subscribers.status = 'subscribed'`.
3. Topic opt-down: if `campaigns.topic_list_id` is set — whether the audience came from
   that list directly, or from a segment, tag, or individual subscriber rule — that
   `list_memberships.status = 'active'` for the subscriber on `topic_list_id`. A campaign
   with no `topic_list_id` skips this check (it isn't tied to a preference-center topic).
4. `campaigns.tier` is accepted by `subscribers.email_frequency` (`FREQUENCY_ACCEPTS` in
   `app/db/enums.py`). Automations are lifecycle emails and skip this check (decided: not
   revisited).

It runs twice: when the audience is frozen into `campaign_recipients`, and again just
before each message is queued (BR-06). A failed check becomes
`campaign_recipients.status = 'skipped'` with a `skip_reason` (`list_opted_out` for rule 3,
`frequency_preference` for rule 4).

### Opt-outs cannot be reactivated by imports

The application must upsert subscribers with `ON CONFLICT (account_id, email) DO UPDATE`
that **never sets `status`**, and add list memberships with `ON CONFLICT DO NOTHING`.
The database backs this up (see `app/db/triggers.py`):

- Inserting a subscriber whose email has an active suppression stores them as `suppressed`,
  whatever status the import asked for.
- `unsubscribed`/`suppressed` → `subscribed` and `opted_out` → `active` raise an error
  unless the transaction ran `SET LOCAL app.allow_resubscribe = 'on'`, which only the
  explicit re-subscription code path does.

**Resolved:** segment/tag campaigns now respect topic opt-outs via `campaigns.topic_list_id`
(nullable, see section 1 and the eligibility rule above). The campaign creation UI should
let the user optionally tag a segment/tag/subscriber-audience campaign with a topic.

---

## 5. Campaign send pipeline

```
campaign_audiences  --(confirm: resolve rules, dedupe by email, eligibility check)-->  campaign_recipients
   (the rules)                                                                         (frozen audience)
                                                                                              |
                                              pre-send re-check per recipient (BR-06)         v
                                                                                        email_messages
                                                                                     (one per recipient)
```

- `campaigns.audience_frozen_at` is set when `campaign_recipients` is written; no rows are
  added afterwards. `eligible_count` = recipients not skipped.
- `campaigns.sending_started_at` marks content and audience immutable (BR-04).
- Checks: `scheduled` needs `scheduled_at`; `scheduled`/`sending`/`sent`/… need a sender and
  `confirmed_at`; `sending` and later need `audience_frozen_at` and `sending_started_at`.
- Returning a scheduled campaign to `draft` (BR-03) must delete its `campaign_recipients`
  and clear `confirmed_at` / `audience_frozen_at`; re-scheduling freezes again.

---

## 6. Message lifecycle — API success is not delivery

```
queued ─▶ submitting ─▶ accepted ─▶ delivered ─▶ (complained)
   │           │            │  └──▶ soft_bounced / bounced
   │           │            └─────▶ rejected
   │           └──▶ failed   (our side, retries exhausted — CMP-14)
   └──▶ cancelled (campaign cancelled before submission)
```

| State | Meaning | Set by |
|---|---|---|
| `queued` | Row created, waiting for a worker | send job |
| `submitting` | Worker is calling the provider API | worker |
| `accepted` | Provider API returned a message ID. **Not delivered.** | worker, from API response |
| `delivered` | Provider `delivery` event received | event processor only |
| `soft_bounced` / `bounced` | Transient / permanent bounce event | event processor |
| `complained` | Spam complaint event | event processor |
| `rejected` | Provider refused after accepting the request | event processor |
| `failed` | Never accepted; retries exhausted | worker |
| `cancelled` | Campaign cancelled before submission | cancel handler |

Enforced: any status from `accepted` onward requires `provider_message_id` and
`accepted_at`; `delivered` requires `delivered_at`.

---

## 7. Events are the source of truth; stats are derived

- `email_events` is append-only. The webhook processor does
  `INSERT … ON CONFLICT (provider, provider_event_id) DO NOTHING` and only updates
  `email_messages` (status, `*_at`, `first_opened_at`, …) and `suppressions` when a row was
  actually inserted — so a redelivered webhook is never counted twice.
- Open/click tracking events use `provider = 'tracking'` with a generated
  `provider_event_id` (e.g. hash of message + type + link + minute).
- `campaign_stats` is written **only** by the aggregator, from `email_events` /
  `email_messages` / `campaign_recipients`. `last_event_id` is the high-water mark, so it can
  be updated incrementally or truncated and rebuilt at any time. Test sends are not counted.
- Metric definitions (PRD 5.2): sent = accepted; delivery rate = delivered / sent;
  open rate = unique opens / delivered; click rate = unique clicks / delivered;
  failures = failed + rejected.

---

## 8. Index review

| Query path | Index |
|---|---|
| Subscriber lookup by email | `uq_subscribers_account_id_email` |
| Subscriber list / filter | `ix_subscribers_account_id_status`, `…_created_at`, `…_external_id` |
| List members | PK `(list_id, subscriber_id)`, partial `ix_list_memberships_list_id_active`, `ix_list_memberships_subscriber_id` |
| Campaign list | `ix_campaigns_account_id_status`, `ix_campaigns_account_id_created_at` |
| Scheduler: due campaigns | partial `ix_campaigns_due (scheduled_at) WHERE status = 'scheduled'` |
| Topic opt-out check at freeze/send | partial `ix_campaigns_topic_list_id WHERE topic_list_id IS NOT NULL` |
| Frozen recipients | `ix_campaign_recipients_campaign_id_status` |
| Send worker | partial `ix_email_messages_pending (queued_at) WHERE status IN ('queued','submitting')` |
| Message by provider ID (webhooks) | `uq_email_messages_provider_message_id` |
| Campaign report | `ix_email_messages_campaign_id_status`, `ix_email_events_campaign_id_event_type` |
| Per-link clicks | `ix_email_events_link_id` |
| Account activity | `ix_email_events_account_id_event_type_occurred_at` |
| Import worker | partial `ix_import_jobs_pending WHERE status IN ('queued','processing')` |
| Import history | `ix_import_jobs_account_id_created_at` |
| Automation trigger lookup | partial `ix_automations_active_trigger_list`, `…_trigger_tag` |
| Automation worker | partial `ix_automation_enrollments_due (next_run_at) WHERE status = 'active'` |
| Suppression check at send | partial unique `uq_suppressions_active_email` (index-only scan) |
| Consent history | `ix_subscription_events_subscriber_id_occurred_at` |

FK columns on large tables that are hit by cascades (`email_messages`, `email_events`,
`subscription_events`, `suppressions`, `automation_enrollments`) all have supporting
indexes. FKs left unindexed point at small, rarely-deleted rows (users, templates, senders).

---

## 9. Check constraints

| Table | Constraint |
|---|---|
| `campaign_audiences` | exactly one of `list_id` / `segment_id` / `tag_id` / `subscriber_id` |
| `automations` | trigger target matches `trigger_type` (list XOR tag); `active` needs a sender |
| `automation_steps` | wait step has duration and no content; email step has content and no wait |
| `automation_enrollments` | `active` needs `next_run_at` |
| `campaigns` | `scheduled_has_time`, `confirmed_before_send`, `frozen_before_send` |
| `campaign_recipients` | `skip_reason` set iff `status = 'skipped'` |
| `email_messages` | exactly one origin (campaign + recipient, or automation); accepted-or-later has provider ID; delivered has `delivered_at` |
| `email_events` | `bounce_type` only on bounce; `link_id` only on click |
| `import_column_mappings` | `custom_field_id` set iff `target = 'custom_field'` |
| `subscriber_field_values` | at most one typed value |

---

## 10. V1 freeze decisions (resolved 2026-10-05)

1. **Auth strategy** (section 2) — **both.** Keep `password_hash`, `user_identities`, and
   `user_sessions` / `auth_tokens`. Local password login ships first; SSO can be linked per
   user later without a schema change.
2. **Topic opt-outs for segment/tag campaigns** (section 4) — **yes.** Added nullable
   `campaigns.topic_list_id`; rule 3 of the eligibility check now applies to any audience
   type, not just list campaigns.
3. **Frequency for automations** — **no.** Automations stay lifecycle emails and bypass the
   `email_frequency` / `tier` check; only campaigns are filtered by it.
4. **`email_events` partitioning** — **not yet.** Ships as a normal table for V1; monthly
   range partitioning is a follow-up migration once send volume justifies the operational
   overhead, not a day-one requirement.

Schema is frozen for V1 as of this decision set.
