# Roadmap

Where this project is going, in the order it should get there. Each milestone below
maps to a **GitHub Milestone**, and each checkbox maps to a **GitHub Issue** on the
project board.

- **Board:** https://github.com/users/Casperinjo/projects/3
- **Issues:** https://github.com/Casperinjo/allsvensk-pred/issues

Rule of thumb for working this: pick the top unblocked issue on the board, move it to
*In Progress*, branch (`feat/<issue-number>-short-slug`), open a PR that says
`Closes #<n>`, let CI go green, merge. The board updates itself.

---

## Status snapshot

**Shipped and running in production** (Cloud Run, `europe-north1`):

- Chronological-split logistic regression on Allsvenskan match data, with form,
  head-to-head, previous-season PPG and Elo features
- `src/fixtures.py` — TheSportsDB fetcher for upcoming fixtures and recent results,
  hardened against rate-limit/non-JSON responses
- FastAPI service: `/upcoming-round`, `/predict-fixtures`, `/track-record`, `/health`
- Firestore persistence: predictions saved write-once as `pending`, graded against
  real results, accuracy exposed via `/track-record`
- Static frontend served from the same origin
- CI (GitHub Actions, pytest) + CD (Cloud Build → Artifact Registry → Cloud Run)

**The honest gaps:** no users, no observability beyond `print`, no relational data,
and the model's accuracy is tracked but never compared to anything a human does.
That last one is the whole point of the next few milestones.

---

## M0 — Process setup

Make the work trackable before adding more of it.

- [x] Create GitHub Project board with Status / Priority / Milestone fields
- [x] Create label taxonomy (`type:*`, `area:*`)
- [x] Create milestones M1–M5
- [x] Seed issues from this roadmap
- [ ] Add a PR template (what changed / why / how tested) — #1
- [ ] Update `README.md` — it still says "scaffolding only, no data or model yet",
      which has been false for about ten commits — #2

**Exit criteria:** every item below this line exists as an issue on the board.

---

## M1 — Observability

**Why first:** this is the cheapest milestone and it pays for every one after it.
M2 is a database migration — you want structured logs *before* you start moving
data, not after you've spent an evening guessing why a write vanished.

- [ ] Replace `print`/bare logging with `structlog` or stdlib `logging` emitting
      JSON lines (Cloud Logging parses JSON into queryable fields; plain strings
      stay opaque blobs)
- [ ] Attach a request ID to every log line and surface it in error responses, so a
      user-reported bug maps to exactly one request trace
- [ ] Log the three things that actually break: TheSportsDB fetch outcomes (status,
      event count, cache hit/miss), persistence failures, and prediction latency
- [ ] Log-based metric + alert policy on error rate — email on sustained 5xx
- [ ] Uptime check against `/health`
- [ ] Error Reporting wired up (it picks up stack traces from logged exceptions
      automatically once severity is set correctly)

**Exit criteria:** you can answer "did anyone hit an error today, and what was the
request?" from the Cloud Console in under a minute, without redeploying.

**Note:** you already log exceptions in the `try/except` around `save_predictions`
and score-on-view. Those are the right call sites — this milestone is about making
their output *queryable*, not about adding more of them.

---

## M2 — Relational data layer (Cloud SQL / MySQL)

**Why second:** everything social is a join. "My points vs. my friends' points over
the last 5 rounds" is one SQL query and a nightmare of client-side fan-out in
Firestore. Migrate before the schema has users in it, not after.

- [ ] Provision Cloud SQL for MySQL (smallest tier; **enable the Cloud SQL Admin
      API** and plan for the Cloud Run connector)
- [ ] Design the schema — start with `matches` and `predictions`, written down as
      real DDL before any code
- [ ] Add SQLAlchemy + Alembic; first migration creates the initial tables
- [ ] Connect from Cloud Run via the built-in Cloud SQL connector (unix socket), not
      a public IP with an allowlist
- [ ] Rewrite `src/store.py` against SQLAlchemy, keeping the *same function
      signatures* (`save_predictions`, `score_predictions`, `load_predictions`) so
      `api/main.py` doesn't change — the existing tests become the safety net
- [ ] Backfill existing Firestore prediction documents into MySQL (one-off script)
- [ ] Point production at MySQL, verify `/track-record` matches the Firestore
      numbers, then decommission the Firestore collection
- [ ] Switch tests to SQLite or a throwaway MySQL container so CI has no cloud
      dependency

**Exit criteria:** `/track-record` returns identical numbers from MySQL, and
`google-cloud-firestore` is gone from `requirements.txt`.

**Design notes:**
- `predictions` wants a real FK to `matches` rather than today's
  document-keyed-by-`match_id` shape. Fixture metadata (teams, kickoff, final score)
  belongs on `matches`; the model's probabilities and pick belong on `predictions`.
- **Store the final score** (`home_score`, `away_score`) on `matches`, not just the
  outcome label. Firestore currently stores only `actual_result`, which is why the
  frontend can't show "Malmö 2–0 AIK". Fixing it in the new schema is free; fixing
  it later is another migration.
- Keep the model's own picks in the same `predictions` table as users' picks (with a
  nullable `user_id`, `NULL` = the model) **or** split them into two tables. The
  single-table version makes "did the user beat the model" one self-join; the split
  version keeps constraints cleaner. Pick one deliberately and write down why.

---

## M3 — User accounts

**Why third:** gamification needs to know whose point it is.

- [ ] `users` table: id, email, password hash, display name, created_at
- [ ] Registration + login with `passlib[bcrypt]` hashing and JWT access tokens
      (FastAPI's `OAuth2PasswordBearer` flow — the canonical tutorial path, and the
      one worth being able to explain in an interview)
- [ ] `get_current_user` dependency guarding authenticated routes
- [ ] `JWT_SECRET` in Secret Manager, injected as a Cloud Run env var — never in
      the image, never in git
- [ ] Email uniqueness + password strength validation, with real error responses
- [ ] Frontend: register / login / logout, token in memory or `httpOnly` cookie
- [ ] Tests: registration, duplicate email, wrong password, expired token,
      protected route without a token

**Exit criteria:** you can register two separate accounts and each sees its own
state.

**Open decision:** roll-your-own JWT (max learning, you own the footguns) vs. Google
OAuth / Firebase Auth (less code, less to explain). Recommendation: roll your own
email+password here *because* it's a learning project, then add "Sign in with
Google" as a second method in M5 once the session plumbing already exists.

---

## M4 — The game: you vs. the model

**Why fourth:** it's the feature that makes the site worth revisiting, and it's
blocked on both of the previous two.

- [ ] `user_picks` table: user_id, match_id, pick (`home`/`draw`/`away`),
      submitted_at — unique on (user_id, match_id)
- [ ] `POST /picks` — submit or change a pick for an upcoming match
- [ ] **Deadline enforcement, server-side:** reject any pick submitted after
      kickoff. Without this the game is trivially cheatable by anyone who waits for
      the result. Client-side countdowns are decoration; the server is the referee.
- [ ] Scoring job that grades user picks when results land, reusing the existing
      `score_predictions` result-fetching path
- [ ] `GET /me/score` — points, record, head-to-head vs. the model
- [ ] Frontend: pick buttons on each upcoming match, locked state after kickoff, a
      "you vs. model" summary
- [ ] Tests: late pick rejected, pick overwritten before deadline, scoring math,
      double-scoring is idempotent

**Exit criteria:** you can submit picks for a round, and after the matches play out
your score and the model's score are both visible and correct.

**Open design question — the point table.** Your stated rule was "the user gets a
point when they're right and the model is wrong." That works, but it means a user
who correctly picks the same favourite as the model scores *nothing*, and the model
is right roughly half the time — so most correct picks feel like they don't count.
Consider something closer to:

| Outcome | Points |
|---|---|
| User right, model wrong | 3 |
| Both right | 1 |
| User wrong | 0 |
| Bonus: correct draw pick | +1 (draws are the hard class) |

Still rewards beating the model, but doesn't punish agreeing with it. Worth deciding
explicitly and documenting, because changing it later invalidates every stored score.

---

## M5 — Social: friends and leaderboards

- [ ] `friendships` table with a request/accept state machine (pending, accepted,
      blocked) — not a bare mutual-follow list
- [ ] `POST /friends/request`, `/friends/accept`, `GET /friends`
- [ ] `GET /leaderboard` — global and friends-only, as a single ranked SQL query
      (window function, not Python sorting after a full table scan)
- [ ] Pagination, and an index on whatever the leaderboard sorts by
- [ ] Frontend: friends list, add-friend flow, leaderboard table with the user
      highlighted
- [ ] Tests: can't friend yourself, can't double-request, leaderboard ordering and
      tie-breaking

**Exit criteria:** two accounts can friend each other and see a shared leaderboard
including the model as a competitor.

---

## Continuous — frontend quality

Not a milestone; a standing concern. Each milestone above ships its own UI, and this
is the list of things that make it not look generic.

- [x] Pick-first layout with expandable probability detail, sporty/bold styling
- [ ] Replace outcome labels with real scorelines in the track record (blocked on
      M2's `home_score`/`away_score`)
- [ ] Team crests or colour identity per club
- [ ] A form/accuracy chart over time, not just a single accuracy number
- [ ] Real empty, loading and error states for every new view (a spinner is not an
      empty state)
- [ ] Mobile layout pass — this is a phone-on-the-sofa app
- [ ] Accessibility: keyboard-navigable pick buttons, visible focus rings, contrast
      check on the pick pill colours
- [ ] Decide whether to stay with vanilla HTML/JS or move to a framework. Vanilla is
      fine and fast today; the point where it stops being fine is auth state + friend
      lists + live leaderboards sharing one page.

---

## Explicitly not doing yet

Parked deliberately, so they stop feeling like a to-do:

- **Kubernetes** — Cloud Run covers this traffic; revisit if there's ever a reason.
- **Model improvements** (xG features, gradient boosting, odds as features) — the
  betting-odds columns and `implied_prob_*` are computed and carried but unused, so
  there's a cheap win sitting there. Still: the app is the weak link right now, not
  the model.
- **Multi-league support** — hardcoded to Allsvenskan (league 4347) and that's fine.
- **Own TheSportsDB API key** — small, annoying, and the shared free key `"3"` is
  rate-limited across every user of it. Do this the next time a fetch fails.
