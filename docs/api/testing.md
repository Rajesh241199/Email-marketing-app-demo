# Testing the API

This covers both ways of testing the backend: the automated `pytest` suite, and exercising
a running instance by hand (Swagger UI or curl). It assumes you've done the setup in
README.md's "Local Development" section.

---

## 1. Automated tests

```bash
cd backend
source .venv/bin/activate   # skip this line if you installed into conda/a system Python instead (Option C)
pytest                      # or: pytest -q
```

Running tests needs the `dev` extra (`pytest`, `httpx`, `ruff`) regardless of how you
installed everything else. `pip install -e ".[dev]"` (Options A/B) already includes it;
if you installed from `requirements.txt` (Option C), add it separately:
`pip install pytest httpx ruff`.

What's going on under the hood (`tests/conftest.py`):

- Tests run against `TEST_DATABASE_URL`, a separate database from your dev one. It must
  already be migrated (`DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head`) - the test
  suite never creates or drops schema itself.
- Each test gets a fresh `db_session` fixture that opens a SAVEPOINT and rolls it back when
  the test ends, so tests never see each other's data and you don't need to wipe the
  database between runs.
- The `client` fixture is a `TestClient` wired to that same session via a `get_db`
  dependency override - call it exactly like a real HTTP client (`client.post("/api/v1/...",
  json=..., headers=...)`).
- Most test files register a user via `POST /api/v1/auth/register` in their own setup to
  get a bearer token, rather than hand-building one - do the same in any test you add.

Run one file or one test while iterating:

```bash
pytest tests/test_campaigns.py -q
pytest tests/test_campaigns.py::test_freeze_respects_topic_opt_out_for_tag_audience -q
```

Lint:

```bash
ruff check app tests
```

---

## 2. Exercising a running instance

Start it (`docker compose up -d && docker compose exec app alembic upgrade head`, or the
Option B/C host-uvicorn paths in the README), then open **`http://localhost:8000/docs`** for
the interactive Swagger UI - every endpoint below is listed there with its schema, and you
can click "Authorize" and paste a bearer token to call authenticated ones directly from the
browser.

The rest of this section is a curl walkthrough of the golden path: register → set up a
sender and a list → add a subscriber → build a campaign → freeze and send it → check stats.

### Register and get a token

```bash
BASE=http://localhost:8000/api/v1

curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" -d '{
  "account": {"name": "Acme Co", "country_code": "US", "address_line1": "1 Main St", "city": "Springfield"},
  "user": {"email": "owner@acme.example", "password": "correct-horse-battery"}
}'
```

The response has `access_token` and `refresh_token`. Save the access token:

```bash
TOKEN=<access_token from the response>
AUTH="Authorization: Bearer $TOKEN"
```

`access_token` expires after `ACCESS_TOKEN_EXPIRE_MINUTES` (15 by default) - use
`POST /api/v1/auth/refresh` with the refresh token to get a new one instead of registering
again. `GET /api/v1/auth/me` is a quick way to check whether a token is still valid.

### Set up a sender

There's no real email-provider integration in this build, so sender verification is a
dev-only stand-in rather than a real SES/domain-auth flow:

```bash
SENDER=$(curl -s -X POST $BASE/senders -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"from_name": "Acme", "from_email": "hello@acme.example"}')
SENDER_ID=$(echo "$SENDER" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X PATCH "$BASE/senders/$SENDER_ID/verify" -H "$AUTH"
```

A campaign can't be confirmed with an unverified sender - this step is required before
the campaign steps below will work.

### Create a list and a subscriber

```bash
LIST=$(curl -s -X POST $BASE/subscribers/lists -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name": "Newsletter"}')
LIST_ID=$(echo "$LIST" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

SUB=$(curl -s -X POST $BASE/subscribers -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"email": "recipient@example.com"}')
SUB_ID=$(echo "$SUB" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X POST "$BASE/subscribers/$SUB_ID/lists/$LIST_ID" -H "$AUTH"
```

Adding a subscriber to a list (or applying a tag, via `POST
/api/v1/subscribers/{id}/tags/{tag_id}`) also enrolls them in any active automation whose
trigger matches - that's the one piece of automation logic that runs synchronously today
(see `app/subscribers/router.py`'s `_enroll_in_matching_automations`); nothing *advances*
an enrollment afterwards (no worker exists yet).

### Build and send a campaign

```bash
CAMP=$(curl -s -X POST $BASE/campaigns -H "$AUTH" -H "Content-Type: application/json" -d "{
  \"name\": \"October newsletter\", \"sender_id\": \"$SENDER_ID\",
  \"subject\": \"Hello!\", \"html\": \"<p>hi</p>\"
}")
CAMP_ID=$(echo "$CAMP" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X POST "$BASE/campaigns/$CAMP_ID/audiences" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"mode\": \"include\", \"list_id\": \"$LIST_ID\"}"

curl -s -X POST "$BASE/campaigns/$CAMP_ID/confirm" -H "$AUTH"
curl -s -X POST "$BASE/campaigns/$CAMP_ID/freeze"  -H "$AUTH"   # -> {"eligible_count":1,"skipped_count":0,...}
curl -s    "$BASE/campaigns/$CAMP_ID/recipients"    -H "$AUTH"   # see who's in and why anyone was skipped
curl -s -X POST "$BASE/campaigns/$CAMP_ID/send"     -H "$AUTH"   # campaign -> "sending", email_messages queued
```

`send` is where this build's scope stops: it queues one `email_messages` row per eligible
recipient (status `queued`) but nothing transmits them - there's no SES/worker integration
yet. A `skip_reason` on a recipient (`suppressed`, `unsubscribed`, `list_opted_out`,
`frequency_preference`, `invalid_email`) tells you exactly which rule in the eligibility
check (schema-v1.md §4) excluded them; set up a suppression, an unsubscribe, or a topic
opt-out first (see below) if you want to see that path exercised.

Stats are computed on demand, not automatically:

```bash
curl -s -X POST "$BASE/campaigns/$CAMP_ID/stats/recompute" -H "$AUTH"
curl -s    "$BASE/campaigns/$CAMP_ID/stats"                -H "$AUTH"
```

### Other lifecycle actions worth knowing about

| Action | Endpoint | Notes |
|---|---|---|
| Schedule for later | `POST /campaigns/{id}/schedule` `{"scheduled_at": "<iso8601, future>"}` | Needs `confirm` first. Nothing flips it to `sending` automatically at that time - there's no scheduler yet; call `send` yourself when ready. |
| Undo a schedule | `POST /campaigns/{id}/unschedule` | Per BR-03: deletes the frozen `campaign_recipients` and returns the campaign to `draft`. |
| Cancel | `POST /campaigns/{id}/cancel` | Works from draft/scheduled/sending; marks pending recipients `cancelled`. |
| Preview a test send | `POST /campaigns/{id}/test-send` `{"to_emails": ["you@example.com"]}` | Records the attempt (`TestSend` row); doesn't actually email anyone - stub only. |

### Topic opt-outs and the eligibility rule

To see `campaigns.topic_list_id` actually exclude someone from a segment/tag-targeted
campaign (the schema-v1.md §10 decision this bootstrap implements):

```bash
# subscriber opts out of the "Newsletter" list via the preference center (see below),
# or directly: PATCH the list_memberships row to opted_out
# then create a campaign with "topic_list_id": "<LIST_ID>" and a tag/segment audience rule
# instead of a list rule - freeze it and check /recipients for skip_reason "list_opted_out"
```

`tests/test_campaigns.py::test_freeze_respects_topic_opt_out_for_tag_audience` is the
scripted version of this if you'd rather read it than run it by hand.

### The preference center (public, token-based - no login)

The link a real unsubscribe/preferences email would contain is a signed JWT with no
expiry, carrying only the subscriber id (`app/preferences/tokens.py`). There's no email
provider wired up to actually send that link, so generate one directly for testing:

```bash
cd backend && source .venv/bin/activate   # or just `cd backend` if using conda/Option C
python3 -c "from app.preferences.tokens import create_preference_token; print(create_preference_token('$SUB_ID'))"
```

```bash
PTOKEN=<token from above>

curl -s "$BASE/preferences/$PTOKEN"                                    # current state
curl -s -X PATCH "$BASE/preferences/$PTOKEN" -H "Content-Type: application/json" \
  -d '{"email_frequency": "weekly_digest"}'                            # or {"lists": [{"list_id": "...", "opted_out": true}]}
curl -s -X POST "$BASE/preferences/$PTOKEN/unsubscribe"                # full unsubscribe
curl -s -X POST "$BASE/preferences/one-click-unsubscribe/$PTOKEN"      # RFC 8058 - bare POST, no body
```

None of these take a bearer token - they're meant to be hit by a browser/email client with
no account login.

### CSV import

The column mapping is sent as a JSON string in a form field alongside the file - the API
doesn't sniff headers for you, it expects you to have already decided the mapping:

```bash
printf 'email,first_name\nnew1@example.com,Alex\nnew2@example.com,Sam\n' > /tmp/subs.csv

curl -s -X POST $BASE/imports -H "$AUTH" \
  -F "file=@/tmp/subs.csv;type=text/csv" \
  -F 'column_mapping=[{"column_index":0,"target":"email"},{"column_index":1,"target":"first_name"}]' \
  -F "target_list_id=$LIST_ID"
```

The response is the finished `ImportJob` (processing is synchronous, so it's done by the
time you get a response) with `imported_count`/`duplicate_count`/`rejected_count`. Row-level
failures (bad email, a custom-field value that didn't cast) are at
`GET /api/v1/imports/{id}/errors`, not in the main response.

### Webhook / tracking events

The webhook endpoint is a simplified flat JSON body, not a real SES/SNS envelope:

```bash
curl -s -X POST $BASE/events/webhook -H "Content-Type: application/json" -d '{
  "provider": "ses",
  "provider_event_id": "evt-1",
  "provider_message_id": "<an email_messages.provider_message_id, if you have one>",
  "event_type": "delivery",
  "occurred_at": "2026-10-05T12:00:00Z"
}'
```

Since this bootstrap's `send` never calls a real provider, no `email_messages` row ever
gets a `provider_message_id` - so there's nothing for a webhook to match against outside of
a test that sets one directly (see `tests/test_events.py`). The two tracking endpoints are
simpler to try as-is, since they're keyed by `email_messages.id` (an integer) rather than a
provider message id:

```bash
curl -sI "$BASE/events/track/open/1.gif"          # returns a 1x1 gif, records an "open" event
curl -sI "$BASE/events/track/click/1?url=https://example.com"   # 302 redirect, records a "click" event
```

### Everything else

Segments, templates/content-blocks/media, automations, and account/accounts-profile
endpoints all follow the same CRUD shape as campaigns/senders/subscribers above - list them
in Swagger UI (`/docs`) rather than duplicating every request shape here. Two things worth
knowing going in:

- **Segments**' `conditions` field takes a small fixed rule shape, not an arbitrary query:
  `{"field": "status"|"tag"|"list"|"custom_field", "op": ..., "value": ...}`, combined by
  the segment's `match_type` (`all`/`any`). See `app/segments/schemas.py` for the exact
  four rule shapes. `GET /api/v1/segments/{id}/preview` is the fastest way to check a
  segment's `conditions` actually match who you expect.
- **Media uploads** (`POST /api/v1/media`) are multipart, same pattern as the CSV import
  above (`-F "file=@...`), and land on local disk under `backend/var/uploads/` in dev.

---

## 3. What's deliberately not testable yet

A few things return a successful response but don't do what they'd do in production - this
is the explicit scope boundary from the bootstrap plan, not a bug:

- `campaigns/{id}/send` queues messages; nothing dispatches them (no SES integration, no
  worker).
- A scheduled campaign's `scheduled_at` passing doesn't trigger anything by itself - no
  scheduler exists yet.
- Automation enrollments are created on list-join/tag-apply, but no worker advances them
  through their steps.
- `senders/{id}/verify` is a direct status flip, not real domain/DKIM verification.
- The events webhook accepts a simplified flat body, not a real SES/SNS envelope.

If a test for one of these would need to assert "and then an email actually sends," that's
a sign the feature belongs to a later pass, not this one.
