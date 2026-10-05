The **Email Marketing Platform** is designed for small and medium-sized businesses, marketing teams, startups, content creators, and organizations that need a straightforward way to manage audiences and execute email campaigns without the complexity of a large marketing suite.


### Core User Journey

```text
Account Setup
    ↓
Business & Sender Verification
    ↓
Subscriber Management
    ↓
Template Creation
    ↓
Campaign Preparation
    ↓
Preview & Test
    ↓
Send / Schedule
    ↓
Automation
    ↓
Analytics
```

---

## Product Objectives

The platform aims to enable users to:

- Create and configure an account with business details.
- Configure and verify sender identities.
- Add, import, organize, and maintain subscriber data.
- Import customer-owned CSV files using flexible column mapping.
- Create and reuse responsive email templates.
- Create, test, send, and schedule marketing campaigns.
- Automatically exclude unsubscribed and suppressed contacts.
- Support subscriber preferences and compliant unsubscribe handling.
- Run basic trigger-based email automations.
- Review campaign delivery and engagement performance.

The product is built around four principles:

- **Simple by default** — users should always understand the next action.
- **Safe to send** — verification, validation, suppression, and confirmation protect sender reputation.
- **Compliant by design** — consent, preferences, and unsubscribe controls are part of the sending workflow.
- **Measurable** — campaigns provide clear delivery and engagement feedback.

---

## Core Capabilities

### Account & Onboarding

- Account registration, sign-in, sign-out, and password recovery.
- Account email verification.
- Business / organization profile.
- Business address and country.
- Account timezone and date/time preferences.
- Sender name, sender email, and reply-to configuration.
- Sender verification and domain-authentication status.
- Onboarding progress and send-readiness validation.

### Subscriber Management

- Manual subscriber creation and editing.
- Search, filtering, and bulk selection.
- Lists / groups.
- Tags.
- Custom subscriber fields.
- Basic segmentation.
- Consent source and consent timestamp.
- Subscriber states including subscribed, unsubscribed, and suppressed / bounced.
- Automatic exclusion of ineligible contacts from marketing sends.

### CSV Import & Field Mapping

The platform supports customer-owned CSV structures rather than requiring a predefined spreadsheet format.

```text
Upload CSV
    ↓
Detect Headers
    ↓
Preview Data
    ↓
Map Columns
    ↓
Ignore Unused Columns
    ↓
Validate Records
    ↓
Import Subscribers
    ↓
Display Import Summary
```

Key capabilities include:

- Flexible source-column mapping.
- Ignore / Do not import option.
- Email validation.
- Duplicate detection.
- Rejected-row reporting.
- Import summary.
- Asynchronous processing for large files.
- Initial design target supporting approximately 20,000 subscribers per import use case.

### Subscription Preference Center

- Secure subscriber-facing preference page.
- Update supported profile fields.
- Opt in or out of configured topics, lists, or communication categories.
- Opt-down experience without requiring full unsubscribe.
- Full unsubscribe from marketing communication.
- Audit-friendly preference and unsubscribe records.
- Eligibility re-check before subsequent campaign or automation sends.

### Template Management

- Create, edit, save, duplicate, search, and delete templates.
- Subject line and pre-header.
- Reusable header and footer areas.
- Responsive email content.
- Text, image, button, divider, and spacer blocks.
- Personalization / merge fields.
- Desktop and mobile preview.
- Required sender identity and unsubscribe elements.
- Accessibility support such as image alt text.

### Campaigns & Mass Sending

- Campaign creation with internal campaign name.
- Sender and reply-to selection.
- Subject and pre-header.
- Audience selection using individual subscribers, lists / groups, or saved segments.
- Eligible-recipient calculation.
- Automatic suppression filtering.
- Template selection and campaign-specific content changes.
- Preview and test email.
- Pre-send validation.
- Immediate or scheduled sending.
- Campaign lifecycle states:
  - Draft
  - Scheduled
  - Sending
  - Sent
  - Partially Failed
  - Failed
  - Cancelled
- Scheduled campaign cancellation.
- Immutable sent campaign content.
- Bounded retries for temporary provider failures.

### Basic Automation

The initial automation model is intentionally simple:

```text
Trigger
   ↓
Email
   ↓
Wait
   ↓
Email
```

Initial triggers include subscriber added to a list / group and tag applied. Automation states are **Draft**, **Active**, and **Paused**. Recipient eligibility is re-checked immediately before every automation send.

### Campaign Analytics

Campaign-level reporting will include:

- Sent
- Delivered
- Delivery rate
- Unique opens
- Open rate
- Unique clicks
- Click rate
- Hard and soft bounces
- Unsubscribes
- Failures
- Per-link click counts

Open metrics should be presented with an appropriate privacy caveat.

---

## Architecture

The platform is a **clean redesign using a modern Python-based architecture**.

The previous legacy implementation may be referenced to understand historical workflows, but deprecated libraries and legacy architectural patterns are not carried into the new codebase.

### High-Level Architecture

```text
                    ┌──────────────────────┐
                    │      Web Client      │
                    │  TypeScript / React  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │       FastAPI        │
                    │        Python        │
                    └──────────┬───────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
        PostgreSQL             S3          Background Queue
   SQLAlchemy / Alembic    File Storage       / Workers
             │                                   │
             │                                   ▼
             │                           Email Provider
             │                                   │
             │                                   ▼
             │                           Provider Events
             │                                   │
             └───────────────────────────────────┘
```

Long-running operations such as subscriber imports, scheduled campaigns, and bulk sends run asynchronously instead of blocking API requests.

---

## Technology Stack

### Backend

- **Python**
- **FastAPI**
- **Pydantic**
- **SQLAlchemy 2.x**
- **Alembic**
- **PostgreSQL**
- **pytest**
- **Ruff**
- **Docker**

### Cloud & Infrastructure

The architecture is designed for managed cloud services and provider abstraction.

Planned capabilities include:

- Email delivery provider integration.
- Object storage for CSV files and media assets.
- Durable background-job processing.
- Delivery, bounce, complaint, open, and click event processing.
- Managed secrets and environment configuration.
- Structured logs and operational monitoring.

AWS services such as **SES, S3, SQS, SNS / EventBridge, and Secrets Manager** can be used where selected by the final infrastructure design.

### Frontend

The application will use a modern TypeScript-based web frontend, with the backend exposed through versioned REST APIs.

---

## Repository Structure

```text
email-marketing-platform/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   ├── db/
│   │   ├── accounts/
│   │   ├── auth/
│   │   ├── senders/
│   │   ├── subscribers/
│   │   ├── imports/
│   │   ├── segments/
│   │   ├── templates/
│   │   ├── campaigns/
│   │   ├── suppressions/
│   │   ├── preferences/
│   │   ├── automations/
│   │   ├── analytics/
│   │   ├── integrations/
│   │   └── workers/
│   ├── migrations/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/
├── docs/
│   ├── architecture/
│   ├── api/
│   └── requirements/
├── .github/
│   └── workflows/
├── .gitignore
├── .env.example
├── docker-compose.yml
└── README.md
```

The repository structure may evolve as implementation progresses.

---

## Core Data Model

The platform uses an account-level normalized subscriber model.

A subscriber exists once within an account and can participate in multiple lists or groups.

```text
Subscriber
   │
   ├── List Memberships
   ├── Tags
   ├── Custom Field Values
   ├── Consent Records
   ├── Preferences
   └── Suppression State
```

Primary domain entities include:

- Account
- User
- Sender
- Subscriber
- List / Group
- List Membership
- Tag
- Custom Field
- Segment
- Import Job
- Template
- Campaign
- Campaign Recipient
- Campaign Event
- Suppression
- Preference / Unsubscribe Event
- Automation

---

## Sending & Eligibility Rules

Recipient eligibility is enforced centrally.

A marketing email must never be sent to a contact who is:

- Unsubscribed.
- Hard bounced.
- Complaint suppressed.
- Otherwise suppressed by platform rules.

Additional core rules include:

- An unverified sender cannot send a campaign.
- Scheduled campaigns must use a valid future date/time.
- A scheduled campaign must return to Draft before editing.
- Once sending starts, campaign audience and content are immutable.
- Subscriber imports must not silently overwrite unsubscribe or suppression states.
- Campaign and automation sends re-check eligibility immediately before sending.
- User-facing scheduling uses the account timezone.

---

## Pre-Send Validation

Before a campaign can be sent, the platform validates:

- Sender is verified.
- At least one eligible recipient exists.
- Suppressed contacts are excluded.
- Subject is present.
- Email content is not empty.
- Required footer is present.
- Links are syntactically valid.
- Unsubscribe mechanism is present.
- Scheduled date/time is valid.
- Test sending is available before final confirmation.

---

## Compliance & Deliverability

Compliance and deliverability are first-class platform requirements.

### Unsubscribe

Every marketing email must include a working unsubscribe mechanism.

The platform supports:

- Visible unsubscribe link in the email body.
- Subscription preference center.
- Standards-based one-click unsubscribe.
- Secure unsubscribe identifiers.
- Immediate eligibility update after unsubscribe.

### RFC 8058 One-Click Unsubscribe

Marketing messages are designed to support:

```http
List-Unsubscribe: <https://example.com/unsubscribe/...>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

The one-click unsubscribe endpoint must:

- Accept HTTPS POST requests.
- Require no login.
- Require no confirmation page.
- Securely identify the relevant recipient/subscription.
- Apply the unsubscribe before the recipient becomes eligible for another marketing send.

### Deliverability

The platform will support:

- Sender verification status.
- SPF / DKIM guidance where supported by the provider.
- Automatic hard-bounce suppression.
- Automatic complaint suppression.
- Provider-aware throttling and queueing.
- Clear errors when sending is blocked.

---

## Security

Security requirements include:

- TLS for data in transit.
- Server-side authentication and authorization.
- Account-level data isolation.
- No secrets exposed to browser clients.
- Secrets stored outside source control.
- Modern credential handling.
- Audit-friendly state changes where appropriate.
- Structured logging and correlation identifiers.
- Input validation for external data.

### Never Commit Secrets

```text
.env
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
DATABASE_PASSWORD
JWT_SECRET
AUTH_CLIENT_SECRET
private keys
API keys
provider credentials
```

Use `.env.example` for configuration documentation and a managed secrets solution in deployed environments.

---

## Reliability & Data Integrity

The implementation is expected to provide:

- Asynchronous processing for long-running imports and sends.
- Idempotent job execution where practical.
- Safe recovery from temporary provider failures.
- Duplicate subscriber prevention.
- Consistent subscriber status transitions.
- Suppression precedence over imported status.
- Provider-event history for analytics and troubleshooting.
- Partial-failure handling without invalidating successful sends.
- Correlation IDs across API requests, background jobs, and provider events.

---

## API Design

The backend uses versioned REST APIs.

Example resource groups:

```text
/api/v1/auth
/api/v1/accounts
/api/v1/senders
/api/v1/subscribers
/api/v1/lists
/api/v1/tags
/api/v1/imports
/api/v1/segments
/api/v1/templates
/api/v1/campaigns
/api/v1/preferences
/api/v1/automations
/api/v1/events
/api/v1/analytics
```

FastAPI-generated OpenAPI documentation will be available in development environments.

---

## Local Development

### Prerequisites

- Git
- Python 3.11+
- PostgreSQL 16 (or Docker / Docker Compose, to run it for you)

### Clone the Repository

```bash
git clone <company-repository-url>
cd email-marketing-platform
```

### Fastest path: the setup script

```bash
cd backend
./setup.sh
```

Handles the virtual environment, dependencies, `.env`, PostgreSQL (installs/starts it on
macOS with Homebrew), the two databases, and migrations in one idempotent run - safe to
re-run any time. It prints the command to start the server when it's done. See
[`docs/getting-started.md`](docs/getting-started.md) for a full walkthrough of what to do
next, or follow the manual steps below if you'd rather do it by hand.

### Environment Configuration

```bash
cd backend
cp .env.example .env
```

Populate `.env` only with local development values. **Never commit `.env`.**

### Option A - everything in Docker

```bash
docker compose up -d        # from the repo root: postgres + the API
docker compose exec app alembic upgrade head
```

The API is then live at `http://localhost:8000` (`/docs` for the Swagger UI).

### Option B - Postgres in Docker, API on the host (faster reload loop)

```bash
docker compose up -d postgres
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Option C - conda / plain pip, no venv (deployment-style)

For an environment that already has its own activation story (a conda base env, a
container base image, a server with a system Python) and doesn't want a project-local
`.venv`, install straight from the pinned `backend/requirements.txt` instead of
`pip install -e .`:

```bash
cd backend
cp .env.example .env            # fill in real values - see "Environment Configuration" above
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Notes:

- `requirements.txt` is the full pinned production dependency closure (no `pytest`/`ruff`/
  `httpx` - those stay in `pyproject.toml`'s `dev` extra, only needed to run tests/lint).
  It's generated from `pyproject.toml`'s `[project.dependencies]`; if you add or change a
  dependency there, regenerate it the same way (`pip install .` into a clean/throwaway
  environment, then `pip freeze` it, dropping the self-referencing
  `email-marketing-platform-backend @ file://...` line).
- The app runs straight from the checked-out code - nothing needs `pip install`-ing the
  project itself, just the dependencies and a working directory inside `backend/` (so
  `app.main:app` and `alembic.ini`'s relative paths resolve).
- `--reload` is a dev convenience (file-watcher) and isn't meant for production; for a real
  deployment run uvicorn as above (or behind a process manager / `--workers N`) without it.
- Everything else - `.env` contents, running migrations, which database it points at - is
  identical to Options A and B above.

### Running the test suite

Tests run against a *separate* database (`TEST_DATABASE_URL` in `.env`) so they never touch
your dev data. Create and migrate it once:

```bash
createdb email_marketing_test   # or: docker compose exec postgres createdb -U postgres email_marketing_test
DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
```

Then, from `backend/`:

```bash
pytest
```

Each test runs inside a rolled-back transaction (see `tests/conftest.py`), so the test
database stays empty between runs.

See `docs/api/testing.md` for a full walkthrough of exercising every endpoint by hand
(curl/Swagger UI), including the parts that need a bit of setup (bearer tokens, the
preference-center token, webhook payloads).

---

## Testing

Automated tests cover the critical business and security behavior called out below. See
`docs/api/testing.md` for how to run the suite and how to exercise the API manually.

- Authentication and authorization (`tests/test_auth.py`).
- Account isolation (every domain's tests include a cross-account 404 case).
- Subscriber CRUD and duplicate prevention (`tests/test_subscribers.py`).
- CSV validation and import processing (`tests/test_imports.py`).
- Suppression rules and recipient eligibility, including the topic-opt-out rule for
  segment/tag campaigns (`tests/test_campaigns.py`).
- Template validation (`tests/test_templates.py`).
- Campaign state transitions and pre-send validation (`tests/test_campaigns.py`).
- Unsubscribe processing, incl. RFC 8058 one-click (`tests/test_preferences.py`).
- Provider-event processing and idempotent webhook ingestion (`tests/test_events.py`).

All tests should pass before merging changes into protected branches.

---

## Observability

Structured logging will cover:

- API failures.
- Authentication and authorization failures.
- Subscriber import jobs.
- Campaign sending jobs.
- Provider API failures.
- Delivery events.
- Bounce events.
- Complaint events.
- Unsubscribe events.

Correlation identifiers should make it possible to trace a workflow across API calls, asynchronous jobs, and provider events.

---

## Development Workflow

Recommended branch model:

```text
main
  │
  └── develop
        │
        ├── feature/<feature-name>
        ├── fix/<issue-name>
        └── chore/<maintenance-name>
```

### Pull Request Guidelines

- Do not push application changes directly to `main`.
- Keep pull requests focused on one logical change.
- Require peer review before merge.
- Ensure automated checks pass.
- Resolve review comments before merge.
- Use meaningful commit and pull-request descriptions.
- Never include credentials or sensitive data in commits.

