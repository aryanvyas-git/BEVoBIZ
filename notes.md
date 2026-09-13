# BEVoBIZ — Project Notes

Everything about BEVoBIZ in one place: what it is, why it's built the way it
is, and how every piece works. Written as study material for a viva/defense
— read top to bottom once, then use the Table of Contents to jump to
whatever question you get asked.

## Table of Contents

1. [One-line summary](#1-one-line-summary)
2. [Problem statement](#2-problem-statement)
3. [Objectives](#3-objectives)
4. [Tech stack](#4-tech-stack)
5. [System architecture](#5-system-architecture)
6. [Database design](#6-database-design)
7. [Authentication & tenant isolation](#7-authentication--tenant-isolation)
8. [Module-by-module walkthrough](#8-module-by-module-walkthrough)
9. [The AI search feature, in depth](#9-the-ai-search-feature-in-depth)
10. [Frontend architecture](#10-frontend-architecture)
11. [API reference](#11-api-reference)
12. [Database migrations](#12-database-migrations)
13. [Testing strategy](#13-testing-strategy)
14. [Design principles / hard rules](#14-design-principles--hard-rules)
15. [Development process (phases)](#15-development-process-phases)
16. [What's deliberately not built](#16-whats-deliberately-not-built)
17. [Glossary](#17-glossary)
18. [Anticipated viva questions](#18-anticipated-viva-questions)
19. [Request lifecycle — how one request is processed](#19-request-lifecycle--how-one-request-is-processed)

---

## 1. One-line summary

BEVoBIZ is a **multi-tenant inventory + sales management SaaS** for small
businesses, with an **AI natural-language search bar** that lets an owner
ask plain-English questions about their own data ("what were my top 5
products last month?") and get back a real, freshly generated SQL answer —
safely, without ever risking another tenant's data or a write to the
database.

**The core engineering problem this project solves is not the CRUD.** Any
inventory app can have products and sales tables. The hard, interesting
problem is: *how do you let an LLM write and execute real SQL against a
production multi-tenant database, on user-supplied natural language input,
without that being a standing security hole?* That's the part worth
presenting in depth.

## 2. Problem statement

Small business owners (a kirana store, a boutique, a small distributor)
track inventory and sales, but:

- Spreadsheets don't scale past a handful of products and get error-prone.
- Off-the-shelf inventory SaaS is often either too complex (built for
  enterprises) or too dumb (no analytics beyond a static report).
- Getting an answer to an ad-hoc question — "which category made me the
  most money this month?" — normally requires either a developer to write
  a query, or navigating a fixed set of canned reports that may not cover
  the question at all.

**BEVoBIZ's answer:** a lightweight, opinionated inventory + sales tracker
where a plain-English question bar sits next to the dashboard and can
answer *any* question about the business's own data — not a fixed list of
reports — by writing fresh SQL on demand, safely.

## 3. Objectives

1. Build a secure, multi-tenant SaaS backend where each business's data is
   fully isolated from every other business's, with no exceptions.
2. Implement inventory CRUD and sales recording with correct, tamper-proof
   historical pricing (a sale must always reflect the price at the time it
   happened, not today's price).
3. Build a natural-language-to-SQL engine that lets a non-technical user
   ask free-form questions about their data.
4. Make that engine **provably safe**: it must be structurally impossible
   for it to write to the database, read another tenant's rows, or read
   sensitive tables (like password hashes) — regardless of what the LLM is
   tricked or fails into generating.
5. Keep the LLM provider swappable (local/free vs. hosted/paid) behind one
   interface, so the product isn't locked into one vendor.
6. Ship a real, working KPI dashboard computed from live data — no mocked
   numbers anywhere in the UI.

## 4. Tech stack

### Backend

| Library | Version | Role |
|---|---|---|
| **FastAPI** | 0.115.6 | Python API framework — async-capable, automatic OpenAPI/Swagger docs, Pydantic-based validation |
| **SQLAlchemy** | 2.0.36 | ORM — maps Python classes to Postgres tables (`app/models/`) |
| **Alembic** | 1.14.0 | Schema migrations — every schema change is a versioned, reviewable Python file |
| **psycopg** (v3) | 3.2.13 | PostgreSQL driver |
| **sqlglot** | 30.17.0 | A real SQL parser (not a regex hack) used to statically analyze and rewrite untrusted LLM-generated SQL — this is the backbone of the AI safety layer |
| **Pydantic** | 2.10.4 | Request/response schema validation (`app/schemas/`) |
| **PyJWT** | 2.10.1 | Signs/verifies JSON Web Tokens for auth |
| **passlib[bcrypt]** | 1.7.4 | Password hashing |
| **groq** | 1.0.0 | Client for Groq's hosted LLM API (default provider) |
| **ollama** | 0.6.2 | Client for a locally-run Ollama LLM server (offline provider) |

### Frontend

| Library | Version | Role |
|---|---|---|
| **React** | 18.3.1 | UI library |
| **Vite** | 5.4.11 | Dev server + bundler |
| **React Router** | 6.28.1 | Client-side routing (`/login`, `/signup`, `/dashboard`) |
| **Axios** | 1.7.9 | HTTP client, with a shared instance that attaches the JWT |
| **Recharts** | 3.10.1 | Bar/pie charts — used both on the dashboard and for NLQ chart results |

### Database & infrastructure

- **PostgreSQL 16** with the **pgvector** extension, run as a Docker
  container (`pgvector/pgvector:pg16` image) via **Docker Compose**.
  pgvector is enabled today but not yet queried by anything — it's
  provisioned ahead of time for a planned retrieval-augmented (RAG) schema
  grounding upgrade once the schema grows past what static context can
  describe well (see [§16](#16-whats-deliberately-not-built)).
- A **second, dedicated Postgres role** (`bevobiz_nlq_reader`) with
  `SELECT`-only grants on exactly three tables, used exclusively by the AI
  query executor. See [§9](#9-the-ai-search-feature-in-depth).

### Why these choices (if asked)

- **FastAPI over Flask/Django:** async support, Pydantic validation built
  in (means fewer hand-written checks), and automatic interactive API docs
  at `/docs` — useful for both development and demoing the API directly.
- **SQLAlchemy + Alembic over raw SQL:** type-safe queries in Python, and
  every schema change is a reviewable, revertible migration file instead
  of manual `ALTER TABLE` commands run by hand.
- **sqlglot over regex/string-matching for SQL safety:** regex cannot
  reliably distinguish "a `DELETE` hidden inside a CTE" from "the word
  DELETE inside a string literal" — a real parser walks an actual syntax
  tree, so the safety checks are structural, not pattern-matching.
- **Groq as the default LLM provider:** free tier, very low latency
  (important for a search bar UX), OpenAI-compatible API. Ollama is kept
  as a fully offline fallback via the same adapter interface.
- **pgvector:** chosen specifically because it's a Postgres extension, not
  a separate vector database service — keeps infrastructure to one
  container while still leaving a clear upgrade path to embedding-based
  retrieval later.

## 5. System architecture

```
┌──────────────┐      JWT (Bearer)      ┌───────────────────────────────────────────┐
│ React (Vite) │ ─────────────────────▶ │              FastAPI backend               │
│ frontend     │ ◀───────────────────── │  auth · products · sales · dashboard       │
└──────────────┘        JSON            │                                             │
                                         │  ┌───────────────────────────────────────┐ │
                                         │  │            NLQ pipeline                │ │
                                         │  │                                         │ │
                                         │  │  schema_context ──▶ LLM adapter         │ │
                                         │  │                        │ (Groq/Ollama)  │ │
                                         │  │                        ▼                │ │
                                         │  │              validator (sqlglot)        │ │
                                         │  │                        │                │ │
                                         │  │           enforce_business_scope        │ │
                                         │  │                        │                │ │
                                         │  │              scoped executor            │ │
                                         │  │        (bevobiz_nlq_reader role,        │ │
                                         │  │      READ ONLY txn, timeout, LIMIT)     │ │
                                         │  └────────────────────────┬────────────────┘ │
                                         └───────────────────────────┼──────────────────┘
                                                                      ▼
                                         ┌───────────────────────────────────────────┐
                                         │         PostgreSQL 16 + pgvector           │
                                         │   businesses · users · products · sales    │
                                         └───────────────────────────────────────────┘
```

**Request flow for a normal (non-AI) action**, e.g. "add a product":

1. Frontend sends `POST /products` with the JWT in the `Authorization`
   header.
2. FastAPI's dependency injection (`Depends(get_current_user)`) decodes the
   JWT, loads the `User` row, and hands the route the authenticated user —
   including their `business_id`.
3. The route uses `current_user.business_id` (never anything from the
   request body) to scope the insert.
4. SQLAlchemy issues the INSERT via the normal app database engine.
5. The response is validated against a Pydantic response model before
   going back to the frontend.

**Request flow for an AI question**, e.g. "what were my top 5 products last
month?" — see [§9](#9-the-ai-search-feature-in-depth) for the full
breakdown; the short version is: JWT gives you a `business_id` → the
question and a hand-written schema description go to the LLM → the LLM's
raw SQL is parsed and validated → every table reference is rewritten to be
pre-filtered to that one `business_id` → it's executed as a locked-down DB
role in a read-only transaction with a timeout and row cap → a second LLM
call turns the resulting rows into a plain-English sentence → the frontend
renders an answer, a table/chart toggle, and the exact SQL that ran.

## 6. Database design

Four tables. Every domain table carries a `business_id` foreign key — this
is the physical mechanism behind multi-tenancy.

```
businesses
├── id (PK)
├── name
└── created_at

users
├── id (PK)
├── business_id (FK → businesses.id, CASCADE)
├── email (unique)
├── password_hash
└── created_at

products
├── id (PK)
├── business_id (FK → businesses.id, CASCADE)
├── name
├── category (nullable)
├── cost_price       (Numeric(12,2))
├── selling_price    (Numeric(12,2))
├── quantity_in_stock
├── reorder_level
├── created_at
└── updated_at

sales
├── id (PK)
├── business_id (FK → businesses.id, CASCADE)
├── product_id  (FK → products.id, CASCADE)
├── quantity              (CHECK quantity > 0)
├── unit_cost_price       (Numeric(12,2))  — SNAPSHOT at time of sale
├── unit_selling_price    (Numeric(12,2))  — SNAPSHOT at time of sale
├── sold_at
└── created_at
```

**Key design decisions:**

- **`Numeric(12, 2)` for all money columns**, never `float`/`double`.
  Floats introduce rounding drift on currency math (`0.1 + 0.2 != 0.3` in
  binary floating point); `Numeric` is exact decimal arithmetic, which is
  what money requires.
- **`business_id` on every domain table**, indexed, with
  `ON DELETE CASCADE` — deleting a business cleans up everything under it,
  and every query can (and must) filter on this column.
- **Snapshot pricing on `sales`.** `sales.unit_cost_price` and
  `sales.unit_selling_price` are copied from the product **at the moment
  the sale is recorded** and never touched again. `products.cost_price`
  and `products.selling_price` are the *current*, editable prices. This
  means: if a product's price changes today, every past sale's recorded
  profit stays exactly what it was when the sale happened. Profit is
  **always** computed as
  `(unit_selling_price - unit_cost_price) * quantity` from the `sales`
  row — never by joining back to `products` for a price. Get this wrong
  and editing a product's price today silently rewrites last month's
  numbers.
- **`CHECK (quantity > 0)`** on `sales` — a database-level constraint, not
  just an application check, so a bad row can never exist even if a bug
  slips past the API layer.
- **No soft deletes** — kept simple for this project's scope; deletions are
  real deletions, cascaded via foreign keys.

## 7. Authentication & tenant isolation

**Signup (`POST /auth/signup`):** creates a new `Business` row *and* the
first `User` row for it in the same transaction. The password is hashed
with **bcrypt** (via `passlib`) before it ever touches the database — the
plaintext password is never stored or logged. A JWT is issued immediately
so the user is logged in right after signing up.

**Login (`POST /auth/login`):** looks up the user by email, verifies the
password against the stored bcrypt hash, issues a JWT on success.

**The JWT itself:** signed with `HS256`, carries the user's `id` as the
`sub` claim and an expiry (`JWT_EXPIRE_MINUTES`, default 24h). It carries
**no** business data directly — every request re-derives `business_id` by
loading the `User` row fresh from the database via the token's user id.
This means revoking/changing a user's business membership takes effect
immediately, without needing to invalidate tokens.

**Every protected route** depends on `get_current_user` (`app/deps.py`),
which:

1. Extracts the Bearer token via FastAPI's `HTTPBearer`.
2. Decodes and verifies the JWT signature and expiry.
3. Loads the `User` row by the `sub` claim.
4. Raises `401 Unauthorized` if any step fails.

**Tenant isolation, concretely:** every single query in every router —
`products`, `sales`, `dashboard` — filters by
`current_user.business_id`, which comes only from the verified token,
**never** from the request body or a query parameter. There is no endpoint
anywhere in the codebase that accepts a client-supplied `business_id`. This
is a hard rule for the whole project (see [§14](#14-design-principles--hard-rules)),
and it's enforced even harder for the AI path — see next.

## 8. Module-by-module walkthrough

### Inventory (`app/routers/products.py`)

Standard CRUD, all scoped to `current_user.business_id`:

- `POST /products` — create.
- `GET /products` — list, with optional `search` (name, case-insensitive
  substring) and `category` filters.
- `GET /products/{id}`, `PUT /products/{id}`, `DELETE /products/{id}` — a
  shared `_get_owned_product()` helper 404s if the product doesn't exist
  *or* belongs to a different business — the two cases are
  indistinguishable to the caller on purpose, so the API never leaks
  "that product exists, it's just not yours."

### Sales (`app/routers/sales.py`)

- `POST /sales` records a sale:
  1. Loads the product **with a row-level lock**
     (`SELECT ... FOR UPDATE`).
  2. Checks `payload.quantity <= product.quantity_in_stock`; rejects with
     `400` otherwise.
  3. Creates the `Sale` row, copying the product's *current*
     `cost_price`/`selling_price` into the sale's snapshot columns.
  4. Decrements `product.quantity_in_stock`.
  5. Commits both changes in one transaction.

  **Why the row lock matters:** without `FOR UPDATE`, two concurrent
  requests selling the last unit of the same product could both read
  `quantity_in_stock = 1`, both pass the check, and both succeed —
  overselling by one unit. The lock forces the second request to wait
  until the first transaction commits (and its stock decrement is
  visible), so the second request re-checks against the *post-decrement*
  quantity.
- `GET /sales` lists sales for the business, with optional `date_from`/
  `date_to` filtering, eager-loading the related product
  (`joinedload`) to avoid an N+1 query problem when rendering product
  names.

### Dashboard (`app/routers/dashboard.py`, `GET /dashboard/stats`)

One endpoint, computed entirely with SQL aggregates over live data — no
number on the dashboard is hand-typed or mocked:

- **Inventory valuation** — cost valuation and retail valuation
  (`SUM(price * quantity_in_stock)`), product counts by stock status
  (in-stock / low-stock / out-of-stock, derived from `reorder_level`).
- **Revenue/profit/units sold** — all-time totals, plus today/this-week/
  this-month breakdowns (computed in one query using conditional
  `CASE WHEN` aggregates rather than three separate queries).
- **30-day sales trend** — one point per day, revenue and units, with
  gap-filling so days with zero sales still appear as zero rather than
  being missing from the series (important for the chart to render a
  continuous line).
- **Top 5 products** by units sold.
- **Sales by category** (uncategorized products bucketed under
  "Uncategorized").
- **Low-stock items** — products at or below their own `reorder_level`.

### Auth schemas & validation

All request bodies are Pydantic models (`app/schemas/`) with basic
length/range validation (e.g. password minimum length, non-negative
prices/quantities) — invalid input is rejected with a `422` before it ever
reaches a database query.

## 9. The AI search feature, in depth

This is the centerpiece of the project — the part to spend the most
presentation time on. **The premise:** an LLM can be prompted to write
SQL, but its raw output must be treated as **completely untrusted input**,
on the same trust level as a hand-typed string from an anonymous user —
because that's functionally what it is. The design principle throughout is
**defense in depth**: five independent layers, each of which alone would
be enough to stop a given class of attack, stacked so that no single bug
or successful prompt injection is suffic to cause damage.

### The pipeline, end to end (`POST /nlq/ask`)

```
question ──▶ schema_context (static prompt) ──▶ LLM.generate() ──▶ raw text
                                                                       │
                                                          sql_extraction.py
                                                     (strip markdown fences,
                                                      prose prefix, etc.)
                                                                       │
                                                                candidate SQL
                                                                       │
                              ┌────────────────────────────────────────┘
                              ▼
                     validator.validate_sql()
              (sqlglot parse → structural allowlist checks)
                              │
                              ▼
                    scope.enforce_business_scope()
           (rewrite every table reference into a tenant-filtered subquery)
                              │
                              ▼
                     executor.run_safe_query()
     (bevobiz_nlq_reader role · READ ONLY txn · 5s timeout · LIMIT 1000)
                              │
                              ▼
                        columns, rows
                              │
                ┌─────────────┴─────────────┐
                ▼                            ▼
     summarize.summarize_answer()      returned as-is to frontend
     (second, separate LLM call,       for the Table/Bar/Pie view
      never touches the DB)
                              │
                              ▼
                 plain-English answer sentence
```

### Layer 1 — Schema context (`app/nlq/schema_context.py`)

A hand-written, carefully worded English description of exactly three
tables (`products`, `sales`, `businesses`) is sent to the LLM as its
*system* prompt on every question. It:

- Deliberately **omits the `users` table entirely** — the model is never
  even told it exists, let alone its columns (password hashes).
- Explicitly explains the snapshot-pricing rule and instructs the model to
  always compute revenue/profit from `sales.unit_cost_price` /
  `unit_selling_price`, and **never** join to `products` for pricing on a
  historical question.
- Explicitly instructs the model to **not** write any `business_id` filter
  at all — scoping is handled entirely outside the model's control (see
  Layer 3). This avoids relying on the model to get tenant scoping right,
  which would be unacceptably fragile.
- Ends with a strict output contract: exactly one PostgreSQL `SELECT`
  statement, nothing else.

This is **static context**, not retrieval-augmented generation (RAG) — the
whole schema is small enough today to just describe in full every time.
pgvector is already provisioned in the database for a future upgrade to
embedding-based retrieval once the schema grows large enough that a full
description stops fitting well in a prompt (see [§16](#16-whats-deliberately-not-built)).

### Layer 2 — SQL extraction (`app/nlq/sql_extraction.py`)

LLMs routinely ignore "output only SQL" and wrap the query in a markdown
code fence or prefix it with "Here's the query:". This module does
best-effort cleanup (strip fences, find the `SELECT`/`WITH` keyword) so
that well-intentioned model output has a fair chance of reaching the
validator in parseable shape. **It adds no safety by itself** — the
extracted text goes through the exact same validation pipeline as if it
had been typed by hand.

### Layer 3 — Structural validation (`app/nlq/validator.py`)

The candidate SQL is parsed with **sqlglot**, a real SQL parser, into an
abstract syntax tree — not scanned with regex. A regex-based blocklist
(`if "DROP" in sql: reject`) fails in both directions: it can be evaded
(`DR/**/OP`, weird casing tricks) and it over-blocks (rejecting the
harmless string `'DROP shipping fee'` as a column value). Walking a real
parse tree instead lets the checks be **structural**:

- Must parse as **exactly one** `exp.Select` node — not an `INSERT`,
  `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, or any
  unrecognized statement type (`exp.Command`, sqlglot's catch-all for
  `GRANT`, `REVOKE`, `COPY`, `CALL`, `LISTEN`, etc — treating this whole
  bucket as disallowed is what makes the check an *allowlist*, "must be
  exactly a SELECT", rather than a blocklist that has to guess every
  dangerous keyword in advance).
- **No stacked statements** (`SELECT 1; DROP TABLE products` parses as two
  statements — rejected).
- **The whole tree is walked, not just the top level** — this specifically
  matters because Postgres allows *data-modifying CTEs*:
  `WITH x AS (DELETE FROM products RETURNING *) SELECT * FROM x` is,
  syntactically, still a `SELECT` at the top level, but it deletes every
  row as a side effect. A check that only looked at the root node would
  miss this entirely; walking every node in the tree catches a `Delete`
  node no matter how deeply it's nested.
- **No `SELECT INTO`** (creates a new table as a side effect).
- **Table allowlist:** only `products`, `sales`, `businesses` may be
  referenced anywhere in the query — `users` is not in the allowlist and
  is therefore structurally unqueryable through this path, and
  schema-qualified references (`pg_catalog.pg_tables`,
  `information_schema.tables`) are rejected outright.
- **Function blocklist** for a specific set of dangerous PostgreSQL
  functions that don't count as "writes" but are still dangerous:
  `pg_sleep` (denial-of-service via a hanging connection),
  `pg_read_file`/`pg_ls_dir` (filesystem access),
  `dblink*` (connects to other databases), `set_config`/`current_setting`
  (session/server state), `lo_import`/`lo_export` (large object
  filesystem I/O), plus anything starting with `pg_`.
- **No SQL comments allowed at all** (`--` or `/* */`), checked with a
  cheap regex *before* parsing even starts — comments are a classic vector
  for smuggling tokens past other tools that don't tokenize them the same
  way sqlglot does; a natural-language question never legitimately needs
  one in its generated SQL, so they're refused outright rather than parsed
  and inspected.

If validation passes, `validate_sql()` returns the **canonicalized** SQL
text (re-generated from the parsed tree) — this is also what guarantees
the "cleaned" query that gets scoped and executed is exactly what was
validated, not the original untrusted string with some other formatting.

### Layer 4 — Mandatory tenant-scoping rewrite (`app/nlq/scope.py`)

This is the most interesting piece of engineering in the whole project and
worth explaining carefully.

**The naive approach** would be to take the LLM's query and wrap it:
`SELECT * FROM (<llm sql>) WHERE business_id = :id`. This **does not
work** in general — it only works if the outer query's result happens to
still expose a `business_id` column, which an arbitrary `SELECT name,
quantity_in_stock FROM products` does not. You can't require the LLM to
always include that column; you also don't want to, since it would leak
into every result and every chart.

**What this project does instead:** it parses the SQL with sqlglot,
finds **every** real table reference anywhere in the tree — the top-level
`FROM`, every `JOIN`, every subquery, every CTE body — and replaces each
one, in place, with a pre-filtered derived table:

```sql
-- before
SELECT name, quantity_in_stock FROM products WHERE category = 'Snacks'

-- after (conceptually)
SELECT name, quantity_in_stock
FROM (SELECT * FROM products WHERE business_id = :__nlq_business_id) AS products
WHERE category = 'Snacks'
```

Because the filter is injected **at the source of every table reference**,
it holds true **regardless of what the outer query does with the rows
afterward** — project, join, group, aggregate, nest in a subquery, put in
a CTE — the row set is already scoped before any of that logic ever runs.
The model could try to write `WHERE business_id = 7` for some other
tenant's id; it would have no effect, because by the time that clause
would run, the table it's filtering has already been replaced with a
subquery containing only rows where `business_id = :the_real_id` (the
authenticated user's own id, injected by the code, not the model).

`business_id` is always passed as a **bound SQL parameter**
(`:__nlq_business_id`), never string-interpolated into the SQL text — this
rules out any possibility of the tenant id itself becoming a SQL injection
vector. (There's a small implementation detail here worth knowing: sqlglot
renders Postgres-dialect placeholders in psycopg's native `%(name)s`
pyformat style, so the code translates that one specific, distinctively-named
token back to SQLAlchemy's `:name` style with a plain string replace — done
safely because the parameter name is deliberately unusual and can't
collide with anything an LLM's SQL text might legitimately contain.)

If, for any reason, this rewrite finds zero tables to replace (which
should be structurally impossible given Layer 3 already guarantees at
least one allowed table is present), it **fails closed** — raises an
error rather than ever executing an unscoped query.

### Layer 5 — Locked-down execution (`app/nlq/executor.py`, `app/nlq/db.py`)

Even after Layers 3 and 4, the query runs under several more independent,
stacked defenses — the design intent is that *any one* of these alone
would still stop a worst-case failure of every other layer:

1. **A dedicated, low-privilege Postgres role**, `bevobiz_nlq_reader`
   (`db/init/002_nlq_readonly_role.sql`), used **only** by this executor —
   the rest of the app connects as the normal app role. This role has
   `SELECT` granted on exactly `products`, `sales`, `businesses`, and
   **no write grant of any kind, on any table, ever** — not just
   "disallowed by app logic," but *physically impossible at the database
   level*. It also has no grant on `users` at all — even a hypothetical
   bug that let a query past Layers 3 and 4 and tried to read `users`
   would be rejected by Postgres itself with a permissions error.
2. **`SET TRANSACTION READ ONLY`** — issued as the first statement of a
   fresh, dedicated connection (Postgres requires READ ONLY to be the
   first statement of its transaction, which is why the executor always
   opens a brand-new connection rather than reusing a pooled one that
   might already be mid-transaction) — belt-and-suspenders on top of the
   role's own lack of write grants.
3. **A 5-second `statement_timeout`**, set with `SET LOCAL` (scoped to
   just this transaction) — bounds how long any single query, including a
   runaway or accidentally-expensive one, is allowed to run.
4. **A hard outer `LIMIT 1000`**, wrapped around whatever the query itself
   does or doesn't limit — `SELECT * FROM (<scoped query>) AS x LIMIT
   :n` — so a query that would otherwise return the entire table is capped
   regardless.

The executor function itself is written to **never trust its own
callers**: even though `app/nlq/qa.py` already calls `validate_sql()`
before calling the executor, `run_safe_query()` re-runs `validate_sql()`
and `enforce_business_scope()` internally anyway, rather than accepting
pre-validated SQL as a trusted argument. This is intentional redundancy —
"this is the only function in the codebase that should ever execute
LLM-generated SQL, so it shouldn't rely on every future caller remembering
to validate first."

### Layer 6 (soft) — Friendly, safe error surfaces (`app/routers/nlq.py`)

`POST /nlq/ask` **always returns HTTP 200** — success or failure is
carried in an `executed: bool` field, with a short, pre-written, safe-to-
display `error` string on failure (e.g. "I couldn't turn that into a safe
query — try rephrasing.") The real exception detail (a raw sqlglot parser
message, a stack trace) is logged server-side only, never sent to the
client — this matters because a raw parser error could itself leak
information about the query structure to someone probing for a bypass.

### The second LLM call — answer summarization (`app/nlq/summarize.py`)

Once safe rows come back, a **second, independent** LLM call turns them
into a one-or-two-sentence plain-English answer. This module:

- **Never touches the database** and **never generates SQL** — it only
  ever sees rows/columns that have already passed the entire safety
  pipeline above.
- **Never raises.** If the LLM is unreachable or errors, it logs a
  warning and returns `None` — the table/chart view in the frontend must
  keep working even if the summarization call fails, since the actual
  data was already successfully fetched.

### Why an LLM adapter interface exists at all (`app/llm/`)

`app/llm/base.py` defines one abstract method, `generate(prompt, system)`.
`app/llm/factory.py::get_llm_adapter()` is the **only** way any code in the
project is allowed to get an LLM client — chosen at runtime by the
`LLM_PROVIDER` env var (`groq` or `ollama`). No router, service, or script
anywhere imports `GroqAdapter` or `OllamaAdapter` directly. This means:

- Swapping from Groq to Ollama (or later, any other provider) is a
  **one-file change** (`factory.py`) plus a new adapter module — nothing
  else in the codebase, including the two NLQ call sites, ever changes.
- Both adapters translate provider-specific exceptions (auth failure, rate
  limit, model not found, connection refused) into one common
  `LLMAdapterError` with a message that's already safe to show a user —
  callers never need provider-specific error handling.

### The frontend side of NLQ

- `NlqSearchBar.jsx` — the search input on the dashboard.
- `NlqResultPanel.jsx` — renders the plain-English answer headline, plus a
  segmented Table / Bar / Pie **view toggle** and an expandable "Show
  query" section with the exact SQL that ran (transparency — the user can
  always see what was actually executed).
- `NlqChart.jsx` — **generic** charting with no hardcoded column names: it
  inspects whatever columns the query happened to return and decides
  whether/how to chart them, degrading to a friendly "this result can't be
  charted" message when the shape doesn't fit a bar/pie view (e.g. too
  many columns, no numeric column).

## 10. Frontend architecture

```
frontend/src/
├── App.jsx                 — routes: /signup, /login, /dashboard (protected)
├── context/AuthContext.jsx — holds the JWT + current user, login/logout/signup actions
├── components/
│   ├── ProtectedRoute.jsx  — redirects to /login if not authenticated
│   ├── Sidebar.jsx         — nav shell for the dashboard
│   ├── DashboardHome.jsx   — KPI tiles + charts, calls GET /dashboard/stats
│   ├── InventoryView.jsx   — product table + CRUD modals
│   ├── ProductForm.jsx     — add/edit product form (modal)
│   ├── SalesHistoryView.jsx— sales list with date filters
│   ├── RecordSaleModal.jsx — record-a-sale form
│   ├── SalesTrendChart.jsx, SalesByCategoryChart.jsx — Recharts wrappers
│   ├── NlqSearchBar.jsx / NlqSearch.jsx — the AI search input
│   ├── NlqResultPanel.jsx  — answer + table/bar/pie toggle + "show query"
│   ├── NlqChart.jsx        — generic charting for arbitrary query results
│   ├── Modal.jsx, ConfirmDialog.jsx — shared UI primitives
├── api/                    — one thin axios-based module per resource
│   ├── axios.js            — shared instance, attaches Authorization header
│   ├── auth.js (in context), products.js, sales.js, dashboard.js, nlq.js
│   └── errors.js           — shared helper that safely extracts a
│                              displayable message from any API error shape
│                              (fixes a real crash: a 422 validation error
│                              is an array, and rendering an array directly
│                              as a React child crashes the app — this
│                              helper normalizes it to a string first)
├── pages/                  — Login.jsx, Signup.jsx, Dashboard.jsx (shell)
├── utils/format.js, theme.js
└── index.css                — the entire design system (see below)
```

**State management:** no Redux/Zustand — auth state lives in a single
React Context (`AuthContext`), everything else is local component state
plus direct API calls via axios. Appropriate for this app's size; a global
store would be premature complexity here.

**Design system (`index.css`):** a full set of CSS custom properties on
`:root` — colors (`--color-primary`, a coral accent, plus warm-tinted
neutrals), typography (`--font-heading`: Quicksand, `--font-sans`:
Nunito), spacing/radius tokens, and layered shadow tokens — reused by every
component via shared classes (`.btn`, `.input`, `.modal`, `.table`,
`.tab-bar`). This was done as a separate, purely visual pass with **zero**
functional/data changes, and respects `prefers-reduced-motion`.

## 11. API reference

All routes except `/auth/signup`, `/auth/login`, and `/health` require a
`Authorization: Bearer <jwt>` header.

| Method & path | Purpose |
|---|---|
| `POST /auth/signup` | Create a business + its first user, returns a JWT |
| `POST /auth/login` | Authenticate, returns a JWT |
| `GET /auth/me` | Current user + their business |
| `GET /products` | List products (optional `search`, `category`) |
| `POST /products` | Create a product |
| `GET /products/{id}` | Get one product |
| `PUT /products/{id}` | Update a product (partial) |
| `DELETE /products/{id}` | Delete a product |
| `GET /sales` | List sales (optional `date_from`, `date_to`) |
| `POST /sales` | Record a sale (stock-checked, snapshot-priced) |
| `GET /dashboard/stats` | All KPI/chart data for the dashboard, one call |
| `POST /nlq/ask` | Natural-language question → safe SQL → answer + rows |
| `GET /health` | Liveness check |

Interactive Swagger docs are auto-generated by FastAPI at `/docs` — a good
thing to have open during a live demo as a backup/supplement.

## 12. Database migrations

Managed with **Alembic**, one file per schema change under
`backend/alembic/versions/`:

1. `41e0bb1c342f_create_businesses_and_users_tables.py`
2. `67c3767b069c_create_products_table.py`
3. `13602b1facbe_create_sales_table.py`
4. `67caa59f6edc_add_reorder_level_to_products.py`

Each migration has an `upgrade()` and a `downgrade()` — schema changes are
reviewable diffs and reversible, not manual, undocumented `ALTER TABLE`
statements run by hand against a live database.

## 13. Testing strategy

`backend/scripts/test_sql_safety.py` is a standalone script (run directly
against a real database, not a mocked one) that exercises the entire NLQ
safety pipeline end-to-end with **23 cases**:

- **Valid queries** that must parse, scope, and execute correctly.
- **A dedicated cross-tenant test** that deliberately tries to filter to a
  *different* business's `business_id` inside the query, asserting the
  result set still only contains the authenticated tenant's rows — i.e.
  it doesn't just check that attacks are *rejected*, it checks that
  scoping actually *holds* under an adversarial attempt to override it.
- **A zero-row-result test** — confirms `columns` is still populated
  correctly even when a query legitimately returns no rows (a real bug
  this project hit and fixed: an empty result used to report empty
  `columns` too, which broke the frontend's table rendering).
- **Attack cases**, every one of which must be rejected: `DROP TABLE`,
  `DELETE`, `UPDATE`, stacked statements, a writable CTE
  (`WITH x AS (DELETE ... RETURNING *) SELECT * FROM x`), querying
  `users`, trailing/block SQL comments, `pg_sleep`, `INSERT`,
  `SELECT INTO`, `information_schema` access, `pg_catalog` access,
  `TRUNCATE`, `GRANT`, `REVOKE`, `COPY`, `CALL`, and an empty query.

Other scripts under `backend/scripts/` (`test_llm.py`,
`test_nlq_pipeline.py`, `test_nlq_endpoint.py`, `test_dashboard_endpoint.py`)
are manual/exploratory smoke tests used during development against a real
running backend, rather than an automated CI suite.

## 14. Design principles / hard rules

These four rules were treated as non-negotiable throughout the project
(they're recorded verbatim in the project's own `CLAUDE.md`):

1. **Tenant isolation.** Every domain table has a `business_id`. Every
   query — read or write, anywhere, including the AI path and any future
   admin tooling — is scoped to the authenticated user's own business.
   Zero cross-tenant access, ever.
2. **AI search is read-only, structurally.** The NLQ engine may only ever
   generate and execute `SELECT` statements — enforced by the multi-layer
   safety pipeline in [§9](#9-the-ai-search-feature-in-depth), not by
   prompting the model nicely and hoping.
3. **Snapshot pricing.** Sale line items store their own
   `unit_cost_price`/`unit_selling_price` at the moment of sale. Historical
   profit is always computed from those snapshot columns, never from a
   product's current price.
4. **One LLM adapter.** All LLM access goes through a single interface
   (`app.llm.get_llm_adapter()`); swapping providers is a one-file change.

## 15. Development process (phases)

The project was built in six deliberate, sequential phases, each shipped
and manually tested before the next began (visible directly in the git
history):

1. **Foundation & Auth** — scaffolding, Docker Compose (Postgres+pgvector),
   Alembic, `businesses`/`users` tables, JWT signup/login/me, protected
   React routes.
2. **Inventory CRUD** — `products` table + endpoints + UI.
3. **Sales recording** — `sales` table with snapshot pricing, stock
   locking, recording UI.
4. **NL-to-SQL engine** — the swappable LLM adapter, the sqlglot safety
   layer, the scoped executor, `POST /nlq/ask`. (RAG-based schema
   grounding deliberately deferred — see next section.)
5. **Search bar UI** — the natural-language search bar, plain-English
   answer, table/bar/pie toggle, "show query" transparency panel.
6. **Polish & hardening** — the dedicated read-only Postgres role for NLQ
   (closing the last deferred security gap from phase 4), a global
   exception handler so no endpoint ever leaks a raw stack trace,
   consistent loading/error/empty states app-wide, a fix for a real
   frontend crash risk (rendering a 422 validation array directly as a
   React child), and input validation on every write endpoint.

A separate, purely visual UI/UX redesign pass followed — warm color
palette, rounded corners, Quicksand/Nunito typography, motion — with **no**
functional or data changes, confined entirely to `frontend/src/index.css`
and shared component classes.

## 16. What's deliberately not built

Being explicit about this is itself a deliberate choice — a more honest
signal to evaluators than presenting the project as if everything
imaginable is finished:

- **RAG-based schema grounding for the NLQ engine.** Currently the model
  gets a static, hand-written schema description on every call. This
  works well while the schema is two tables; pgvector is already enabled
  in Postgres specifically so that, once the schema grows large enough
  that a full description stops fitting a prompt well, relevant schema
  fragments can be retrieved by embedding similarity instead of sent in
  full every time.
- **Suppliers & purchase orders, multi-location/warehouse support, deeper
  analytics** — present in the sidebar as disabled "Coming soon" items,
  not implemented.
- **No automated CI test suite** — the safety-critical NLQ pipeline has a
  real, repeatable test script (23 cases); the rest of the app was tested
  manually phase-by-phase rather than with an automated pytest suite.

## 17. Glossary

| Term | Meaning here |
|---|---|
| **Multi-tenancy** | One application instance and one database serving many independent customers ("tenants" — here, businesses), with each tenant's data isolated from every other's. |
| **Tenant/business scoping** | The practice of filtering every query by the current tenant's id so no query can ever see another tenant's rows. |
| **JWT (JSON Web Token)** | A signed, tamper-evident token that encodes who a user is; the server verifies its signature instead of looking up a session in a database on every request. |
| **ORM (Object-Relational Mapper)** | A library (SQLAlchemy here) that lets you work with database rows as Python objects instead of writing raw SQL by hand. |
| **Migration** | A versioned, reviewable script that changes the database schema (Alembic here), so schema history is tracked like code. |
| **Text-to-SQL / NL-to-SQL** | Using an LLM to translate a natural-language question into a SQL query that answers it. |
| **Prompt injection** | An attack where user-controlled text tries to manipulate an LLM into ignoring its instructions — the reason this project never trusts the LLM's output and instead structurally re-validates every query, independent of what the prompt told the model to do. |
| **AST (Abstract Syntax Tree)** | The parsed, structured representation of code (here, SQL) that a real parser produces — what lets `sqlglot` reason about SQL *structurally* instead of via string/regex matching. |
| **RAG (Retrieval-Augmented Generation)** | Feeding an LLM only the most relevant slice of a larger knowledge base (found via similarity search over vector embeddings) instead of the whole thing — the planned future use of pgvector here. |
| **pgvector** | A PostgreSQL extension that adds a vector data type and similarity search, letting a normal Postgres database also serve as a vector store for embeddings. |
| **Snapshot pricing** | Copying a price onto a transaction row at the moment it happens, so later price changes can't retroactively alter historical records. |
| **Row-level lock (`SELECT ... FOR UPDATE`)** | A database lock on specific rows that forces concurrent transactions touching the same rows to wait their turn, preventing race conditions like overselling stock. |
| **Read-only transaction** | A Postgres transaction mode (`SET TRANSACTION READ ONLY`) that makes any write attempted inside it fail at the database level, regardless of application-level checks. |

## 18. Anticipated viva questions

**Q: What's the single most important design decision in this project?**
A: Treating LLM output as fully untrusted input and enforcing safety
structurally (parser-based validation + a rewrite that scopes every table
reference + a database role that's physically incapable of writing),
rather than relying on prompting the model to "please only write SELECTs
and please filter by business_id." Prompts can be ignored, misread, or
adversarially manipulated; a parsed AST and a database permission grant
cannot.

**Q: How do you actually stop the AI from reading another business's
data?** A: `enforce_business_scope()` rewrites the query's own tables —
`products` becomes `(SELECT * FROM products WHERE business_id = :id) AS
products` — *before* the rest of the query runs, so the row set is already
restricted no matter what the outer query selects, groups, or joins. The
`business_id` value comes from the JWT-authenticated user server-side,
never from the model or the request. This is verified by a dedicated
automated test that tries to override it.

**Q: What if the LLM generates a DELETE or DROP?** A: It's rejected before
it ever reaches the database — `validate_sql()` parses the text and
requires the entire parsed tree to be exactly one `SELECT`, walking the
*whole* tree (not just the top level) specifically because Postgres allows
data-modifying CTEs that are technically "a SELECT" at the root but delete
rows as a side effect. Even in the hypothetical case that check had a bug,
the query executes as a Postgres role that has no write grant on any table
— the database itself would refuse the write.

**Q: Why not just use an ORM to build the query instead of raw SQL from an
LLM?** A: That would mean hand-coding every possible question in advance
(a fixed report list), which defeats the actual goal — answering *arbitrary*
natural-language questions. The interesting/hard part of this project is
making free-form LLM-generated SQL safe to run, not avoiding it.

**Q: How would this scale to more tables / a bigger schema?** A: Two
places: the schema description sent to the LLM would need to move from
static text to retrieval (pgvector is already provisioned for exactly
this), and the `ALLOWED_TABLES`/`TABLE_FILTER_COLUMNS` allowlist and the
readonly role's grants would need one new line each per new queryable
table — deliberately a manual, explicit step ("fails closed by design," in
the SQL role file's own comment) rather than something new tables get
automatically.

**Q: Why snapshot pricing instead of just storing a foreign key to the
product and joining for price?** A: A product's price changes over time,
but a past sale's actual revenue/profit shouldn't retroactively change
just because today's price is different. Storing the price *at the moment
of sale* on the sale row itself makes historical numbers immutable and
correct by construction, instead of relying on nobody ever editing a price
without also fixing every affected historical report.

**Q: What would you do differently / what's the biggest weakness?** A: No
automated CI test suite outside the NLQ safety script; the RAG-grounding
work is scaffolded (pgvector enabled) but not implemented, so it doesn't
yet get tested with a genuinely large schema; and the LLM's SQL-generation
*quality* (does it answer the question well, not just safely) isn't
covered by an automated eval set — only its safety is.

**Q: Why FastAPI instead of Django/Flask?** A: Built-in async support,
Pydantic-based request/response validation with almost no boilerplate, and
automatic OpenAPI/Swagger docs at `/docs` for free — useful both for
development and for demoing the raw API.

**Q: Is the JWT itself secure?** A: Signed with `HS256` using a server-side
secret (`JWT_SECRET`), carries only the user id and an expiry — no
sensitive data embedded in the token itself. It's verified (signature +
expiry) on every request via a shared dependency (`get_current_user`), and
the user's current `business_id` is always re-loaded fresh from the
database rather than trusted from an old token payload.

## 19. Request lifecycle — how one request is processed

Two different diagrams, because a normal CRUD request and an AI-search
request actually travel through different machinery once they reach the
backend. Both start and end the same way — browser to `axios` to FastAPI
and back — but what happens in between is worth being able to draw from
memory.

### 19a. A normal request — e.g. "add a product" (`POST /products`)

```
┌─────────────┐
│   Browser    │  1. User submits the "Add product" form
│  (React UI)  │
└──────┬───────┘
       │ 2. axios instance (frontend/src/api/axios.js) attaches
       │    Authorization: Bearer <jwt>  from AuthContext
       ▼
┌──────────────────────────────────────────────────────────┐
│                    FastAPI  (app/main.py)                 │
│                                                             │
│  3. CORSMiddleware checks the request's Origin             │
│     against FRONTEND_ORIGIN                                │
│                                                             │
│  4. Route matched: POST /products  (app/routers/products.py)│
│                                                             │
│  5. FastAPI resolves this route's Depends():                │
│     ┌───────────────────────────────────────────────────┐ │
│     │ get_current_user (app/deps.py)                     │ │
│     │  a. HTTPBearer extracts the token from the header   │ │
│     │  b. decode_access_token() verifies signature+expiry │ │
│     │     → 401 immediately if invalid/expired            │ │
│     │  c. db.get(User, sub_claim)  — loads the user row    │ │
│     │     fresh from Postgres (never trusted from the      │ │
│     │     token payload beyond the id)                     │ │
│     └───────────────────────────────────────────────────┘ │
│     ┌───────────────────────────────────────────────────┐ │
│     │ get_db (app/database.py) — opens a SQLAlchemy       │ │
│     │ Session for this request only, closed after         │ │
│     └───────────────────────────────────────────────────┘ │
│                                                             │
│  6. Pydantic validates the JSON body against ProductCreate  │
│     → 422 immediately if a field is missing/invalid/out of  │
│       the allowed length/range                              │
│                                                             │
│  7. Route body runs:                                        │
│     Product(business_id=current_user.business_id, **payload)│
│     — business_id ALWAYS comes from the verified user,      │
│       never from the request body                           │
│                                                             │
│  8. db.add(product); db.commit(); db.refresh(product)       │
│     → SQLAlchemy issues the INSERT via app.database.engine  │
└───────────────────────────┬─────────────────────────────────┘
                             ▼
                  ┌────────────────────┐
                  │   PostgreSQL 16     │
                  │   INSERT INTO       │
                  │   products (...)    │
                  └────────┬───────────┘
                             │ 9. new row returned
       ┌─────────────────────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│  10. Response serialized against ProductResponse           │
│      (Pydantic) — only the declared fields go out,         │
│      nothing extra leaks                                    │
│  11. If anything above raised an uncaught exception,        │
│      app.main's global exception_handler catches it and     │
│      returns a clean {"detail": "Internal server error"}    │
│      (500) — the real traceback is logged server-side only  │
└───────────────────────────┬─────────────────────────────────┘
                             ▼
┌─────────────┐
│   Browser    │  12. axios resolves, React re-renders the
│  (React UI)  │      product list with the new row
└─────────────┘
```

Every other conventional route (`products`, `sales`, `dashboard`, `auth`)
follows this exact same shape — JWT verified → user loaded → business_id
taken from the verified user → Pydantic validates in and out → SQLAlchemy
talks to Postgres through the one shared app engine.

### 19b. An AI-search request — `POST /nlq/ask`

This one is worth drawing separately because after step 5 (auth) it
**never touches the app's normal database session at all** — it hands off
to an entirely separate pipeline with its own database connection.

```
┌─────────────┐
│   Browser    │  1. User types a question into the search bar
└──────┬───────┘
       │ 2. axios sends POST /nlq/ask  {question}  + JWT
       ▼
┌──────────────────────────────────────────────────────────┐
│  3. get_current_user — same JWT verification as any other  │
│     route (see 19a). This is the ONLY thing this endpoint   │
│     shares with the normal request path.                    │
│     current_user.business_id is captured here and nowhere   │
│     else — the pipeline below never re-derives it.           │
└───────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────┐
│  4. question_to_sql_and_run(question, business_id)          │
│     (app/nlq/qa.py)                                          │
│                                                               │
│     a. schema_context.SCHEMA_DESCRIPTION (static, hand-       │
│        written) sent as the LLM's system prompt               │
│     b. get_llm_adapter().generate(question, system=schema)    │
│        → Groq or Ollama, chosen by LLM_PROVIDER               │
│     c. extract_sql_from_response() strips markdown fences/    │
│        prose the model added despite instructions             │
│                                                                │
│     ┌── untrusted candidate SQL string ──────────────────┐    │
│     │  d. validate_sql()      — sqlglot parse; must be    │    │
│     │     exactly one SELECT, allowlisted tables only,     │    │
│     │     no writes anywhere in the tree, no comments       │    │
│     │     → ValidationError if it fails (safe to show user) │   │
│     │                                                        │   │
│     │  e. enforce_business_scope() — rewrites every table    │   │
│     │     reference into                                      │   │
│     │     (SELECT * FROM t WHERE business_id=:id) AS t        │   │
│     │     using the business_id captured in step 3 — the      │   │
│     │     model's SQL text has no influence over this value   │   │
│     └────────────────────────┬──────────────────────────────┘   │
│                               ▼                                   │
│     f. run_safe_query() (app/nlq/executor.py)                     │
│        opens a FRESH connection on nlq_engine                     │
│        (app/nlq/db.py) — a SEPARATE engine from the app's          │
│        normal DATABASE_URL, authenticated as the                  │
│        bevobiz_nlq_reader Postgres role                            │
│          i.   SET TRANSACTION READ ONLY                            │
│          ii.  SET LOCAL statement_timeout = 5000                   │
│          iii. execute wrapped in an outer LIMIT 1000               │
└───────────────────────────┬───────────────────────────────────────┘
                             ▼
                  ┌─────────────────────────────┐
                  │        PostgreSQL 16          │
                  │  connected as                 │
                  │  bevobiz_nlq_reader            │
                  │  (SELECT-only grant on          │
                  │   products/sales/businesses,     │
                  │   no grant on users at all)       │
                  └────────────┬──────────────────┘
                                │ columns, rows
       ┌────────────────────────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│  5. summarize_answer(question, columns, rows)                │
│     (app/nlq/summarize.py) — a SECOND, independent LLM call, │
│     never touches the database, never generates SQL,          │
│     never raises (returns None on failure so the table/chart  │
│     view still works even if this call fails)                  │
└───────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────┐
│  6. AskResponse assembled: question, answer, generated_sql,  │
│     columns, rows, executed=true, error=null                  │
│     — always HTTP 200; failures set executed=false and a      │
│       short pre-written `error` string instead of raising     │
└───────────────────────────┬─────────────────────────────────┘
                             ▼
┌─────────────┐
│   Browser    │  7. NlqResultPanel renders the plain-English
│  (React UI)  │     answer + Table/Bar/Pie toggle (NlqChart);
└─────────────┘     "Show query" reveals generated_sql verbatim
```

**The one sentence to remember from this diagram:** a normal request
proves *who you are* once (JWT) and then trusts the server's own code for
everything after; an NLQ request proves who you are once too, but then
treats every subsequent step as adversarial — parser validation, a
mandatory rewrite, a different low-privilege database role, and a
read-only transaction — because the SQL running at the end of the pipeline
was written by a model, not by this codebase.
