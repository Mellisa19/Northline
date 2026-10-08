# Northline — Credit & Recovery Intelligence

A working product, not a mockup: a lender's loan book becomes a daily list of accounts to
act on, ranked by the money at stake, with the playbook to run, the outcome recorded, and a
ledger that says honestly how much of it was down to the intervention.

Four surfaces sit on one engine:

- **The marketing site** (`/`) — sparse by design, with a live portfolio board and an
  interactive demonstration of why *ordering* a worklist matters.
- **The workspace** (`/app`) — the product itself, behind a session: triage queue, Account 360,
  recovery ledger, roll-rate reporting, signal feed, playbook library, coverage and model card,
  plus team management for administrators.
- **Accounts** (`/sign-in`, `/sign-up`) — organisations, five roles, server-side sessions.
- **A lead magnet** (`/triage`) that scores an uploaded loan tape with the same engine.

---

## Running it

Two processes. The API must be on port 8010 because the frontend dev server proxies `/api`
to it.

```bash
# terminal 1 — API (creates and seeds the demo book on first run)
cd northline/backend
pip install -r requirements.txt
python serve.py --port 8010

# terminal 2 — web
cd northline/frontend
npm install
npm run dev
```

Then open **http://localhost:5180**.

Ports are set in `frontend/vite.config.js` and `backend/serve.py`. To rebuild the demo book
from scratch: `python seed.py --force` in `backend/`.

---

## Signing in

Seeding creates a demo organisation with one person per role, so every part of the product can
be looked at without signing up:

| Email | Role | Password |
|---|---|---|
| `admin@northline.ng` | Administrator | `northline2026` |
| `risk@northline.ng` | Risk Manager | `northline2026` |
| `analyst@northline.ng` | Credit Analyst | `northline2026` |
| `collections@northline.ng` | Collections Officer | `northline2026` |
| `field@northline.ng` | Field Recovery | `northline2026` |

The sign-in page lists them, and one click fills the form. Signing up creates a new
organisation with you as its administrator.

**What is gated, and what is not.** Deliberate, and the line a real lender would draw:

- **Private** — `/api/worklist`, `/api/accounts/*`, `/api/org/*`. Anything that can name a
  borrower or reveal the queue.
- **Public** — aggregate portfolio reporting, the playbook library, the model card, the
  ordering demo and the triage tool. These carry the argument and expose no individual
  borrower; the public ordering demo returns `sector · city` in place of a company name.

Passwords are hashed with PBKDF2-HMAC-SHA256 (240,000 rounds, per-user salt) from the standard
library. Sessions are opaque tokens stored server-side, so signing out and removing a person
both actually revoke access rather than asking a browser to forget something.

---

## Google sign-in

Real OAuth 2.0 — the authorisation-code flow, run on the server. No simulated login, no
hardcoded user, no demo bypass.

### Setting it up (about five minutes)

**1. Create a Google Cloud project**

1. Go to <https://console.cloud.google.com/>.
2. Top bar → the project dropdown → **New project**. Name it `Northline`, then **Create**.
3. Make sure the new project is selected in that same dropdown.

**2. Configure the consent screen**

1. Left menu → **APIs & Services** → **OAuth consent screen**.
2. User type: **External** → **Create**.
3. App name `Northline`, your email as the support address and developer contact → **Save and
   continue**.
4. **Scopes** → **Save and continue** without adding any. The defaults include everything this
   app needs (`openid`, `email`, `profile`).
5. **Test users** → **Add users** → add the Google account you will sign in with. While the app
   is in *Testing* mode only these accounts can sign in. That is fine for development; add each
   person who needs to try it.

**3. Create the credentials**

1. **APIs & Services** → **Credentials** → **Create credentials** → **OAuth client ID**.
2. Application type: **Web application**. Name it `Northline local`.
3. Under **Authorised JavaScript origins** → **Add URI** → `http://localhost:5180`
4. Under **Authorised redirect URIs** → **Add URI** →
   `http://localhost:5180/api/auth/google/callback`
   This must match exactly: same scheme, same host, same port, same path, no trailing slash.
5. **Create**. A dialog shows the **Client ID** and **Client secret**. Copy both.

**4. Put them in the environment**

```bash
cd northline/backend
cp .env.example .env      # if you have not already
```

Edit `backend/.env`:

```ini
GOOGLE_CLIENT_ID=1234567890-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-secret-here
APP_BASE_URL=http://localhost:5180
GOOGLE_REDIRECT_URI=http://localhost:5180/api/auth/google/callback
```

`.env` is gitignored. Never commit it, never paste the secret into the frontend, and never send
it in a chat. Restart `python serve.py`; the startup log tells you whether it took:

```
Google sign-in: enabled
  redirect URI registered with Google must be exactly: http://localhost:5180/api/auth/google/callback
```

If it says `NOT configured`, it also lists exactly which variable is missing.

### How the flow works

```
browser            backend                     Google
  |  click -------->  |
  |                   |  store single-use state, 302
  |  <----------------|
  |  -------------------------------------------------->  consent screen
  |  <--------------------------------------------------  ?code=...&state=...
  |  ----------------->  |
  |                     |  verify state (single use), POST code + SECRET
  |                     |  ----------------------------------------->
  |                     |  <-----------------------------------------  access token
  |                     |  GET /userinfo with that token
  |                     |  find-or-create the user, issue a one-time code
  |  <------------------  302 /auth/callback?code=<one-time>
  |  ----------------->  POST /api/auth/google/session { code }
  |  <------------------  { token, user }   ← the session token travels in a body, not a URL
```

Decisions worth knowing about:

- **The client secret never leaves the server.** It is sent only in the server-to-server token
  exchange.
- **The identity is trusted because we fetched it ourselves.** The access token comes back from
  Google directly to our backend over TLS in exchange for the secret — it is not supplied by the
  browser, so there is no JWT signature to take on faith.
- **The session token never appears in a URL.** The callback redirect carries a single-use code
  that expires in two minutes, so the long-lived credential stays out of browser history,
  referrer headers and server logs.
- **`state` is single-use and expires in ten minutes.** It is deleted the moment it is read, so a
  replayed callback cannot open a second session.
- **`?redirect=` is restricted to a path on this site**, so the callback cannot be turned into an
  open redirect that launders our domain.
- **Accounts are matched by Google subject first, email second.** An email is only used to attach
  a Google identity to an existing account when Google says that address is verified — an
  unverified address cannot be used to take over an account. A role is never escalated by signing
  in with Google.
- **New Google users get their own workspace** with themselves as administrator, exactly as the
  sign-up form produces.
- **Google-linked accounts have no usable password.** A random unguessable secret is stored, so
  the password form cannot be used against them.

### When it is not configured

The button is hidden and the API answers `503` for `/api/auth/google/start` rather than
pretending. While running `npm run dev` the sign-in page also prints which variable is missing.
Administrators can check the current state and the exact URI to register:

```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8010/api/org/sso-status
```

### Security notes

- **Secrets** live only in `backend/.env`, which is gitignored, or in real environment variables,
  which always take precedence. `.env.example` is committed and contains placeholders. The client
  secret is used solely in the server-to-server token exchange and is never sent to the browser —
  the built frontend bundle was checked and contains no secret material.
- **Error messages are deliberately vague to the user and specific in the log.** Google's own
  error body is logged server-side and never echoed to the person signing in.
- **Protected endpoints are enforced by the server**, not by hiding interface. `/api/worklist`,
  `/api/accounts/*` and `/api/org/*` return `401` without a valid session whether or not any
  JavaScript ran.
- **Sessions are revocable.** Tokens are stored server-side, so signing out and removing a team
  member both invalidate immediately rather than waiting for an expiry.
- **One tradeoff worth knowing:** the session token is kept in `localStorage` and sent as a
  `Bearer` header. That is the standard single-page-app pattern and it is immune to CSRF, but it
  is readable by any script running on the page, so a cross-site scripting flaw would expose it.
  The alternative — an `HttpOnly`, `SameSite` cookie — removes that exposure but reintroduces CSRF
  and requires moving the API and interface onto one origin. Given this app is same-origin in
  production anyway, switching to cookies later is a contained change to `lib/api.js` and the
  session endpoints. It is not done yet, and it is the first thing I would harden before real
  borrower data is involved.

---

## What is real, and what is simulated

This matters, so it is stated in the product as well as here.

**Real:** every number on screen is computed at request time from the SQLite database. Roll
rates, migration matrices, vintage curves, expected recovery, the holdout comparison and the
advance-warning statistics are all derived from the data. Nothing is hard-coded, and reseeding
changes every figure on the site.

**Simulated:** the portfolio itself. It is a generated book of 1,100 Nigerian SME facilities
(670 live, 380 closed, ~50 written off) produced by a documented simulation in
`backend/app/generate.py`. It is internally coherent — one latent stress process drives cash
flow, repayment behaviour, collection actions and recovery — but it is not real borrower data
and carries no information about any actual lender. The interface says so in the rail, the
footer and the API's `/api/meta`.

**The consequence you should care about:** the model's *assumptions* are invented, its
*arithmetic* is not. Replacing the generator with a real loan tape is the whole of the work
needed to make the output real, and the engine will not care where the rows came from.

---

## Architecture

```
northline/
├── backend/
│   ├── app/
│   │   ├── config.py      domain constants: products, sectors, playbooks, costs, weights
│   │   ├── db.py          SQLite schema and connection handling
│   │   ├── generate.py    the portfolio simulation (deterministic; seed 20261005)
│   │   ├── scoring.py     the Northline Risk Index — nine documented components
│   │   ├── priority.py    expected-value prioritisation and review-budget comparison
│   │   ├── playbooks.py   playbook selection and rationale
│   │   ├── analytics.py   portfolio reporting, worklist assembly, ROI ledger
│   │   ├── operations.py  write path: log a contact, capture a promise, settle it
│   │   ├── auth.py        password hashing, sessions, roles, the seeded demo team
│   │   ├── google.py      Google OAuth: state, code exchange, identity linking
│   │   ├── auth_api.py    sign up / in / out, Google endpoints, team management
│   │   ├── env.py         dependency-free .env loader
│   │   └── api.py         FastAPI surface, gating middleware
│   ├── .env.example       committed template; .env itself is gitignored
│   ├── tests/             76 tests: engines, access control, Google sign-in
│   ├── seed.py            build the demo book
│   └── serve.py           run the API (seeds on first run)
└── frontend/
    ├── src/
    │   ├── styles/tokens.css    design tokens: warm palette, shape, motion, type scale
    │   ├── lib/
    │   │   ├── api.js           request client, token handling, response cache
    │   │   ├── auth.jsx         session context
    │   │   ├── motion.js        reveal, count-up, scroll progress, dismiss, debounce
    │   │   └── format.js        money, dates, band and risk tones
    │   ├── components/
    │   │   ├── ui.jsx           Reveal, CountUp, Avatar, Select, Segmented, Ticker, Spinner
    │   │   └── charts.jsx       hand-built SVG: trend, migration heatmap, vintages
    │   ├── site/                marketing page, triage tool, auth pages
    │   └── app/                 workspace: shell + nine screens
    └── verify/                  headless render check (see below)
```

No charting library, no component library, no state manager, no CSS framework, no animation
library. The only frontend dependencies are React, React DOM and an icon set. Charts and the
dropdown are written by hand so the data language and the interaction language stay consistent.

### Motion

Every duration and easing curve is a token (`--dur-*, --ease-*`), and every animation is
opt-out through `prefers-reduced-motion`. Scroll reveals use one `IntersectionObserver` pattern
per element via the `useInView` hook; headline figures ease to their value with `useCountUp`
driven by `requestAnimationFrame`; charts draw themselves with `stroke-dashoffset`; the
workspace cross-fades between screens. Nothing animates at a speed nobody chose.

---

## The engines, and the assumptions they rest on

Every one of these is exposed in the product, because a lending model that cannot be argued
with in a credit committee is not usable.

### Risk index (`scoring.py`)

A transparent weighted index, 0–100, summing to exactly 100 points across nine components:
delinquency 39, cash-flow decline 16, arrears depth 12, broken promises 10, debt-service load
7, payment behaviour 6, first-payment default 5, obligation creep 3, balance erosion 2.

It is an **index, not a calibrated probability of default**, and the product says so on every
screen that shows it. Weights are policy judgement set by hand — not learned from outcomes —
and are published in full in the model card.

### Prioritisation (`priority.py`)

Expected incremental recovery from working an account today:

```
value_at_stake  = min(balance, arrears + 3 × instalment)   # what is reachable this cycle
probability     = max(band floor, risk index ÷ 100)        # chance it is lost if left alone
loss_at_risk    = value_at_stake × loss_given_default × probability
expected_recovery = loss_at_risk × playbook effectiveness
```

The value at stake is deliberately *not* the whole remaining balance. Treating a three-year
facility as fully at risk because one instalment is twenty-six days late is how a worklist ends
up ranking large loans above urgent ones.

The same endpoint returns what the conventional ordering — days past due, then size — would
reach over the same number of reviews. On the demo book that produces a **diminishing-returns
curve**, which is the honest shape of the claim:

| Reviews per day | Ordering by expected recovery captures |
|---:|---:|
| 10 | 7.9× what an arrears-ordered list reaches |
| 25 | 3.6× |
| 50 | 1.6× |
| 100 | 1.3× |
| 300 | 1.0× |

Ordering only matters when the team is the constraint. With enough capacity to work the whole
actionable book, every ordering reaches the same accounts and the advantage vanishes. The
product shows this comparison live rather than quoting a headline number, and a test pins the
curve's shape so it cannot quietly become a marketing figure.

The mechanism is easier to see than the ratio. At forty reviews a day, the arrears ordering
spends twenty-five of them on accounts already past 90 days, where the best available playbook
converts about one in seven. Ordering by expected recovery spends them on the 1–60 day bands,
where the same effort converts about one in three.

### Playbooks (`playbooks.py`, `config.py`)

Nine playbooks with owner, timing, script, success measure, channel cost, and a published
conversion rate per delinquency band. These conversion assumptions are the most arguable
numbers in the system, so they are printed rather than buried.

### Analytics (`analytics.py`)

- **Roll rates and migration** are rebuilt from dated cash movements into a `band_history`
  table at seed time — month-end delinquency positions reconstructed from actual payments, not
  from a month-end spreadsheet. Write-off and closure appear as a real exit column.
- **Vintage curves** take the running maximum per cohort, because cumulative default cannot
  fall; a curve that dipped would mean the denominator moved.
- **Advance warning** is measured, not asserted: the first inflow decline dated before the
  account first reached 31 days past due, over accounts that did so inside the window the
  transaction history covers. It is reported both for the whole book and for accounts that
  actually carry a monitoring consent.
- **The ROI ledger** separates gross collections from the holdout comparison, and refuses to
  publish an incremental estimate when the sample is too small or the two arms are not
  balanced on severity. Most cash on a delinquent book arrives without a phone call, and
  presenting it as the effect of intervention would be dishonest.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/meta` | Liveness; seed, as-of date, synthetic-data disclosure, form vocabularies |
| GET | `/api/portfolio/summary` | KPIs, PAR 30/60/90 by count and value, band and risk distributions, monitoring coverage |
| GET | `/api/portfolio/par-trend` | Monthly portfolio-at-risk series |
| GET | `/api/portfolio/migration` | Band migration matrix with exit column |
| GET | `/api/portfolio/vintages` | Cumulative default by cohort |
| GET | `/api/portfolio/advance-warning` | Detection rate and lead-time distribution |
| GET | `/api/portfolio/coverage` | Consent coverage, tiers, blind spots |
| GET | `/api/portfolio/ordering-demo` | Public ordering comparison, anonymised to `sector · city` |
| GET | `/api/portfolio/featured-case` | Public worked example, anonymised to a sector description |
| POST | `/api/auth/signup` · `/signin` · `/signout` | Create an organisation, start a session, revoke it |
| GET | `/api/auth/providers` | Which sign-in methods this server can offer |
| GET | `/api/auth/google/start` | 302 to Google's consent screen; `503` when unconfigured |
| GET | `/api/auth/google/callback` | Google returns here; 302 back to the app with a one-time code |
| POST | `/api/auth/google/session` | Trade that code for a session token |
| GET | `/api/org/sso-status` | What to register with Google, and what is missing *(administrators only)* |
| GET | `/api/auth/me` · `/auth/roles` · `/auth/demo` | Current user, available roles, seeded demo team |
| GET | `/api/org/team` | Members of your organisation |
| POST | `/api/org/team` | Add a member with a role *(administrators only)* |
| DELETE | `/api/org/team/{id}` | Remove a member and revoke their sessions *(administrators only)* |
| GET | `/api/worklist` 🔒 | Ranked queue + baseline comparison. Filters: `budget`, `officer`, `band`, `product`, `search` |
| GET | `/api/accounts/{id}` 🔒 | Account 360: risk, playbook, expected value, schedule, payments, signals, cash flow, timeline, siblings |
| POST | `/api/accounts/{id}/actions` 🔒 | Log a contact attempt, optionally capturing a promise |
| POST | `/api/accounts/{id}/promises/{pid}/resolve` 🔒 | Keep or break a promise; keeping it settles the oldest arrears and moves the band |
| GET | `/api/recovery/summary` | ROI ledger and performance by playbook, channel and officer |
| GET | `/api/playbooks` | Catalogue with effectiveness by band and logged performance |
| GET | `/api/alerts` | Signal feed, including signals that are not actionable for want of consent |
| GET | `/api/scoring/model-card` | Weights, bands, limitations, planned work |
| POST | `/api/triage` | Score an uploaded loan tape with the same engine |
| GET | `/api/triage/template` | Download a template CSV |

🔒 requires `Authorization: Bearer <token>`, obtained from `/api/auth/signin`. Everything else
is reachable without a session. Interactive docs at `http://127.0.0.1:8010/docs`.

---

## The closed loop

Reading a worklist is not a product. On an account page you can record a contact and capture a
dated promise; marking that promise **kept** inserts a real payment, settles it against the
oldest overdue instalment, recomputes arrears and days past due, moves the delinquency band and
updates the current reporting point in the band history. The recovery ledger, the promise-kept
rate and the officer statistics all move as a result.

That write path (`operations.py`) is what produces the outcome data that a future
outcome-trained model would learn from. It is deliberately the first thing built, not the last.

---

## Verification

**Backend** — 76 tests (`cd backend && python -m pytest tests -q`), in three groups.

*Engines (25):* the shape and reproducibility of the generated book, reconciliation between the
current account position and the reconstructed band history, monotonicity of the risk index, the
expected-value engine's boundary behaviour, playbook selection and the decay of its published
conversion rates, consent gating of transaction signals, and the full write loop including
rejection of invalid channels and dispositions. They also pin the diminishing-returns curve of
the ranking claim and the ledger's refusal to publish an estimate it cannot support.

*Access control (14):* salted password hashing, weak-password rejection, sign-up creating an
organisation with an administrator, duplicate-email handling, sign-in refusing a wrong password
without revealing which emails exist, session resolution and server-side revocation, garbage and
malformed tokens, the public/private boundary, an administrator-only team mutation, self-removal
being blocked, and removal revoking the removed person's sessions.

*Google sign-in (37):* configuration read from the environment and the default redirect URI;
the authorisation URL carrying every required parameter with the secret absent; open-redirect
paths rejected; `state` being single-use, expiring and unguessable; the one-time exchange code
being single-use and expiring; the token exchange posting the right form to Google; Google's
error text never reaching the user; network failure handled; the userinfo call sending the bearer
token; a new Google user getting their own workspace with no usable password; a returning user
being matched by subject with their display name refreshed; linking to an existing password
account without changing its role and without breaking its password; an unverified email being
refused to prevent takeover; two Google identities not claiming one email; the endpoints'
redirects for a cancelled consent screen, a missing code, an unknown state and a failed exchange;
and `sso-status` being administrator-only and never echoing the secret.

`httpx` is stubbed in those tests, so they never touch the network and need no real credentials.

**Frontend** — `npm run verify` builds a separate bundle, signs in against the API, plants the
session the way the sign-in form would, and renders every surface inside jsdom. It asserts that
expected content is present and that nothing wrote to `console.error`. It reports:

```
PASS  Landing / Triage / Sign in / Sign up / OAuth callback
PASS  Worklist / Account 360 / Recovery ledger / Reporting
PASS  Signals / Playbooks / Coverage / Model card / Team
14/14 surfaces rendered cleanly
```

This exists because the development sandbox has no browser. It catches the failure that matters
most — a page that throws on real data and renders nothing — but it cannot judge how anything
*looks* or how it *moves*. Both still need a person with a browser.

**Verified live, without a browser:** the redirect to Google is built correctly and contains no
secret; the callback returns a 302 with the right `Location` for a cancelled consent screen, a
missing code, an unknown state and an unconfigured server; the dev-server proxy passes those
redirects through unchanged; the schema migration added the Google columns to the existing
database without losing the five seeded users; `/api/auth/providers` reports honestly; and
password sign-in still works alongside it.

**Not yet verified:** the interactive part — a person actually choosing a Google account and
being returned. That needs a browser and a real Google account, so it is the first thing to do
once credentials exist. Also unverified: the write path driven by hand, the sign-up flow in a
browser, and review of the playbook scripts by a practising collections officer.

---

## Deliberately not built

No loan origination system, no borrower mobile app, no consumer credit bureau, no live bank
API monitoring. Monitoring is selective by design: a live transaction feed is only paid for
where the exposure justifies it, which on the demo book covers about a quarter of accounts and
about two thirds of book value. The unmonitored remainder is worked from the lender's own
records, and the blind spot is reported as a number rather than hidden.

Contact limits, prohibited channels and consent scope are enforced in the engine, not in a
policy document.
