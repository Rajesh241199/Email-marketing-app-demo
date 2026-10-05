# Getting started

What this is, how to get it running, and a tour of every feature. For a strict
endpoint-by-endpoint testing reference (exact request/response shapes, curl for every
route), see [`docs/api/testing.md`](api/testing.md) — this doc is the friendlier "what can
I do with it" walkthrough.

## 1. Run the setup script

```bash
cd backend
./setup.sh
```

This is safe to run more than once — every step checks whether it's already done first.
It will:

- Create a Python virtual environment (`.venv`) and install all dependencies.
- Create `.env` from `.env.example` if you don't have one yet.
- Make sure PostgreSQL 16 is installed and running (on macOS with Homebrew, it will
  install/start it for you; otherwise it tells you to run
  `docker compose up -d postgres` from the repo root, or install Postgres yourself).
- Create the `email_marketing` and `email_marketing_test` databases and the `citext` /
  `pgcrypto` extensions they need.
- Run the database migrations on both databases.

When it finishes, it prints the command to start the server.

**Already have your own environment (conda, a container, a server with its own Python)
and don't want a project-local `.venv`?** Skip the script and install from the pinned
`backend/requirements.txt` instead — see "Option C" in the README's Local Development
section:

```bash
cd backend
cp .env.example .env            # then fill in real values
pip install -r requirements.txt
alembic upgrade head
```

The rest of this guide (running the server, every feature below) is identical either way
— `requirements.txt` and `.venv` both land on the exact same code and dependencies, just
installed differently.

## 2. Start the API

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

The API is now at `http://127.0.0.1:8000`. Open **`http://127.0.0.1:8000/docs`** in a
browser — that's a full interactive UI (Swagger) listing every endpoint, with "Try it out"
buttons that let you call them right from the page. Click **Authorize** in the top right
and paste a bearer token (see step 3) to try authenticated endpoints without typing curl
commands.

`--reload` restarts the server automatically whenever you edit a file — handy while
developing, drop it for a normal run. To make it reachable from another device on your
network, use `--host 0.0.0.0` and visit `http://<this-machine's-IP>:8000/docs` instead.

## 3. A tour of what you can do

Every feature below is a real, working REST API under `/api/v1/...` — nothing here is a
mockup. Each section says what it's for, the main endpoints, and anything non-obvious. All
endpoints except the two marked **public** require a bearer token from step 3a.

### 3a. Accounts & authentication (`/api/v1/auth`, `/api/v1/accounts`)

This is where everything starts. One call creates both your business account and your
first (owner) user:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register -H "Content-Type: application/json" -d '{
  "account": {"name": "Acme Co", "country_code": "US", "address_line1": "1 Main St", "city": "Springfield"},
  "user": {"email": "owner@acme.example", "password": "correct-horse-battery"}
}'
```

The response has an `access_token` (use it as `Authorization: Bearer <token>` on every
other call, valid 15 minutes) and a `refresh_token` (trade it for a new access token at
`/api/v1/auth/refresh` instead of logging in again). Other things here: `/auth/login`,
`/auth/logout` (and `/logout-all` to sign out everywhere), `/auth/me`, email verification
and password reset (both create a token in the database rather than emailing it — no email
provider is wired up yet, see `docs/api/testing.md` for how to grab one for testing).

`/api/v1/accounts/me` is your business profile (address, timezone, branding) — get and
update it. `/api/v1/accounts/me/onboarding-status` tells you whether you're "send-ready"
yet (i.e., have at least one verified sender).

### 3b. Senders (`/api/v1/senders`)

The "From" identity your campaigns send as. Create one, then verify it — there's no real
domain/DKIM check wired up yet, so verification is a direct, dev-only status flip:

```bash
curl -X POST .../senders -d '{"from_name": "Acme", "from_email": "hello@acme.example"}' ...
curl -X PATCH .../senders/<id>/verify ...
```

A campaign can't be confirmed for sending until its sender is verified. `sending_domains`
(DKIM/SPF/DMARC status tracking) live here too, for when a real provider integration adds
actual domain authentication.

### 3c. Subscribers, lists, tags, custom fields (`/api/v1/subscribers`)

Your audience. Subscribers can belong to multiple **lists** (e.g. "Newsletter"), have
**tags** applied (e.g. "VIP"), and carry **custom field** values (any account-defined field
— text, number, date, boolean, or a fixed choice list). All are plain CRUD:

```bash
curl -X POST .../subscribers -d '{"email": "a@example.com"}' ...
curl -X POST .../subscribers/lists -d '{"name": "Newsletter"}' ...
curl -X POST .../subscribers/<sub_id>/lists/<list_id> ...      # join a list
curl -X POST .../subscribers/<sub_id>/tags/<tag_id> ...        # apply a tag
```

Joining a list or getting a tag applied also silently enrolls the subscriber in any
matching **automation** (see 3i) if one is active — that's the one piece of automation
logic wired up end-to-end today.

A subscriber's `status` (subscribed/unsubscribed/suppressed) is never directly editable
here — it only changes through the preference center (3h) or a provider bounce/complaint
event (3k), by design, so compliance history stays consistent.

### 3d. Segments (`/api/v1/segments`)

A saved, dynamic filter over your subscribers — evaluated fresh every time it's used,
rather than a fixed list of members. A segment's rules are a small fixed shape, not a
free-form query:

```json
{"match_type": "any", "conditions": [
  {"field": "status", "op": "eq", "value": "subscribed"},
  {"field": "tag", "op": "has", "value": "<tag_id>"}
]}
```

`GET /api/v1/segments/{id}/preview` runs the rules right now and returns a count plus a
sample of matching subscriber IDs — the fastest way to sanity-check a segment before using
it as a campaign audience.

### 3e. Templates, content blocks, media (`/api/v1/templates`, `/api/v1/content-blocks`, `/api/v1/media`)

Reusable email content. A **template** has a subject, preheader, and body content, plus
optional shared **header/footer blocks** (edit the block once, every template using it
picks up the change — a campaign, once created, is a frozen copy and unaffected).
`POST /api/v1/templates/{id}/duplicate` clones one. `POST /api/v1/media` uploads an image
(multipart) for use inside template content.

### 3f. CSV import (`/api/v1/imports`)

Bring in subscribers from a spreadsheet. You decide the column mapping (which CSV column
is the email, which is a custom field, etc.) and send it alongside the file:

```bash
curl -X POST .../imports \
  -F "file=@subscribers.csv" \
  -F 'column_mapping=[{"column_index":0,"target":"email"},{"column_index":1,"target":"first_name"}]' \
  -F "target_list_id=<list_id>"
```

Processing happens immediately (synchronously) and the response already has the final
counts — imported, updated, duplicate, rejected. Bad rows (invalid email, a value that
didn't match a custom field's type) don't fail the whole import; check
`GET /api/v1/imports/{id}/errors` for exactly which rows and why. Importing never
overwrites an existing unsubscribe/suppression, even if the file says otherwise — that
safety rule is enforced by the database itself (see `docs/architecture/schema-v1.md`), not
just the application code.

### 3g. Campaigns (`/api/v1/campaigns`) — the core workflow

This is the most involved feature, and it's a sequence of steps rather than one call:

1. **Create** a draft: name, sender, subject, content.
2. **Add an audience rule**: target a list, a segment, a tag, or one subscriber — and
   optionally mark a rule `"mode": "exclude"` to subtract from everyone else included.
3. **Confirm**: checks the sender is verified, subject/content are present, and at least
   one audience rule exists.
4. **Freeze**: resolves every audience rule into an actual list of recipients, runs each
   one through the eligibility check (not suppressed, not unsubscribed, respects a topic
   opt-out if you set `topic_list_id`, respects their frequency preference), and records
   anyone excluded with a `skip_reason` you can inspect via `GET /{id}/recipients`.
5. **Send**: queues a message per eligible recipient.

```bash
curl -X POST .../campaigns -d '{"name": "October newsletter", "sender_id": "<id>", "subject": "Hi!", "html": "<p>hi</p>"}' ...
curl -X POST .../campaigns/<id>/audiences -d '{"mode": "include", "list_id": "<list_id>"}' ...
curl -X POST .../campaigns/<id>/confirm ...
curl -X POST .../campaigns/<id>/freeze ...
curl -X POST .../campaigns/<id>/send ...
```

Other actions: `/schedule` (set a future send time), `/unschedule` (back to draft, clears
the frozen audience), `/cancel`, `/test-send` (records the attempt, see the honesty note
below), and `/links` (tracked links for click-reporting).

**Be aware**: `send` queues messages but nothing transmits them yet — there's no email
provider connected in this build. That's intentional scope, not a bug; see §4 below.

### 3h. Preference center (`/api/v1/preferences`) — public, no login

The page a subscriber reaches from a link in an email, to manage their own preferences —
so these endpoints take a signed token in the URL instead of a bearer token:

```bash
curl .../preferences/<token>                                    # see current state
curl -X PATCH .../preferences/<token> -d '{"email_frequency": "weekly_digest"}'
curl -X POST  .../preferences/<token>/unsubscribe                # full unsubscribe
curl -X POST  .../preferences/one-click-unsubscribe/<token>      # RFC 8058 one-click
```

A subscriber can lower their frequency, opt out of one topic list without unsubscribing
from everything, or fully unsubscribe — each writes an audit entry
(`subscription_events`), per the compliance design in `docs/architecture/schema-v1.md`.

### 3i. Automations (`/api/v1/automations`)

A simple trigger → wait → email sequence (e.g. a welcome series). Create one with a
trigger (someone joins a list, or gets a tag), add ordered steps (`wait` with a duration,
or `email` with content), and set it `active` (requires a sender). As noted in 3c,
enrollment happens automatically when the trigger condition occurs. **What doesn't happen
yet**: nothing advances an enrollment through its steps on a timer — that needs a
scheduler this build doesn't have (see §4).

### 3j. Analytics (`/api/v1/campaigns/{id}/stats`)

Campaign performance, aggregated from the event log: delivered, opened, clicked, bounced,
complained, unsubscribed. It's computed on demand, not automatically kept up to date:

```bash
curl -X POST .../campaigns/<id>/stats/recompute ...
curl .../campaigns/<id>/stats ...
```

### 3k. Provider events & tracking (`/api/v1/events`) — public

Where delivery/bounce/complaint notifications would arrive from an email provider, plus
the open-pixel and click-redirect endpoints that generate `open`/`click` events:

```bash
curl .../events/track/open/<message_id>.gif          # 1x1 tracking pixel
curl .../events/track/click/<message_id>?url=https://example.com   # redirect + records a click
```

The webhook endpoint (`POST /api/v1/events/webhook`) takes a simplified flat JSON body
rather than a real provider's signed envelope — see §4.

## 4. What's not real yet (by design)

A handful of actions succeed but don't do the "real world" thing yet, because the
infrastructure for it (an email provider, a background worker/scheduler) isn't part of
this build:

- Sending a campaign queues messages; nothing transmits them to an inbox.
- A scheduled campaign's send time arriving doesn't trigger anything by itself.
- An automation enrollment is created, but nothing advances it through its steps.
- Sender verification is a direct status flip, not a real domain check.
- The provider webhook accepts a simplified flat payload, not a real SES/SNS envelope.

Everything else — every CRUD operation, the eligibility rule, the preference center, the
import pipeline, analytics aggregation — is real, tested, and works end to end.

## 5. Running the tests

```bash
cd backend && source .venv/bin/activate && pytest
```

See `docs/api/testing.md` for details on what the test suite covers and how it isolates
each test.
