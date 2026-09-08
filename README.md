# Exaqube — Discord Analytics Agent

A small full-stack analytics app over a synthetic Discord dataset: a Postgres-backed FastAPI
service, a React frontend, and — the point of the exercise — a **conversational agent that answers
questions by writing SQL and produces artifacts (charts, Excel, PowerPoint) through a plugin
system**. Adding a new capability means writing **one plugin file** and nothing else.

---

## 1. Running it (assume Docker and nothing else)

```bash
cp .env.example .env          # then set GROQ_API_KEY (see §2)
docker compose up --build     # db → migrate → load → backend → frontend
```

Then open **http://localhost:3000**.

- Frontend: http://localhost:3000
- API: http://localhost:8000 (`/health`, `/docs` for the OpenAPI UI)
- One command brings up the database, runs migrations, **creates the read-only agent role**, loads
  the dataset (idempotently), and starts the backend and frontend. Startup ordering waits for
  *ready*, not *started* (healthchecks + `service_completed_successfully`).

Re-running the data load on its own (idempotent — no duplicate rows):

```bash
docker compose run --rm load        # or: make load
```

Running the tests:

```bash
docker compose run --rm backend pytest -q     # or: make test
```

The dataset CSVs are committed under `data/dataset/` (CC0), so a clean checkout works offline. The
brief's Kaggle link 404s; this is the same-shape `edudev-commons-org` mirror.

---

## 2. Configuration (every variable)

All variables live in `.env.example`. Required values have no default, so a missing one makes the
backend **fail loudly at startup** rather than 500 at request time.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | App role — read/write on app-owned tables (pins). |
| `READONLY_DATABASE_URL` | **Agent role** — the only role generated SQL runs as. |
| `AGENT_RO_PASSWORD` | Password the migration uses to create the read-only role. |
| `POSTGRES_USER/PASSWORD/DB` | Postgres container init. |
| `LLM_PROVIDER` | `groq` (default). Provider abstraction — see §5. |
| `LLM_MODEL` | `openai/gpt-oss-120b` (default). Lighter fallback: `openai/gpt-oss-20b`. |
| **`GROQ_API_KEY`** | **The only thing you must set to run the agent.** Get one free at console.groq.com. |
| `LLM_MAX_COMPLETION_TOKENS` | Caps model output (free-tier token budget). Default 1024. |
| `RESULT_PREVIEW_ROWS` | Rows of a query result shown to the model. Default 15. |
| `AGENT_MAX_STEPS` / `AGENT_MAX_RETRIES` | Bounds the agent loop. |
| `ROW_CAP` / `STATEMENT_TIMEOUT_MS` | Safety: max rows returned / per-statement timeout. |
| `ARTIFACT_DIR` / `ARTIFACT_MAX_ROWS` / `ARTIFACT_MAX_BYTES` / `PPTX_MAX_SLIDES` | Artifact bounds. |
| `DATA_DIR` | Where the dataset CSVs are mounted. |
| `LOG_LEVEL` | Log level. |

**To plug in your own key:** set `GROQ_API_KEY=...` in `.env` and `docker compose up`. That's it.
To use a different provider entirely, see §5.

---

## 3. How to write a new plugin

**This is the core design goal: a new capability is one new file in `backend/app/plugins/builtin/`,
and nothing else changes** — not the agent, not the prompt, not a router. The registry discovers the
file at startup; the agent's tool list and prompt are derived from the registry at runtime.

A plugin subclasses `Plugin` and sets four things plus `execute()`:

```python
# backend/app/plugins/builtin/csv_export.py
from app.plugins.base import Plugin, PluginContext, PluginResult, PluginError
from app.plugins.registry import register


@register
class CsvExport(Plugin):
    name = "csv_export"
    description = "Export a result table to a downloadable CSV file."   # the model reads this
    input_schema = {                                                    # the LLM's arguments, validated
        "type": "object",
        "properties": {"input_ref": {"type": "string"}},
        "required": ["input_ref"],
        "additionalProperties": False,
    }
    consumes = {"table"}                                                # what it can take as chained input

    async def execute(self, args: dict, ctx: PluginContext) -> PluginResult:
        table = ctx.inputs["input_ref"]           # resolved + kind-checked for you
        # ... build the file, then write it through the bounded artifact store:
        info = ctx.artifacts.write_bytes(b"...", "export.csv", "text/csv")
        return PluginResult(kind="artifact", data=info.as_dict(), meta={})
```

What the contract gives you (so you don't reinvent it):

- **Argument validation** — `args` are validated against `input_schema` (JSON Schema) before
  `execute()` runs; a bad call becomes a structured, retryable error the agent can fix.
- **Structured errors** — raise `PluginError(code, message, retryable=...)`. The agent sees the code
  and decides whether to retry with a correction. Never leak a stack trace into `message`.
- **Chaining** — return a `PluginResult(kind=...)`. Kinds are the composition currency:
  `table`, `chart_spec`, `artifact`, `text`. Declare which kinds you accept in `consumes`; the loop
  resolves `input_ref` / `input_refs` handles and checks the kind before calling you.
- **Progress** — `await ctx.emit("tool_progress", {"message": "..."})` streams to the UI.
- **Context** — `ctx` carries the read-only DB session, the artifact store, resolved inputs, and the
  configured limits. Nothing is global.

Drop the file in, restart, and the agent can use it. (We do exactly this live — see the startup log
listing discovered plugins.)

---

## 4. What we built, and what we cut

Scoping was treated as part of the task. The weight went to the plugin system, the agent, and safety.

**Built and verified:**

- **Plugin system** — contract + decorator/directory-scan registry; tool list & prompt derived at
  runtime. *(largest weight)*
- **Four plugins** — `query`, `chart`, `excel`, `powerpoint`. (query + chart + excel were the core
  commitment; **powerpoint and pinning were planned cuts that landed because the core came together
  faster than budgeted.**)
- **Agent loop** — NL→SQL→execute→explain; bounded retry; decline; multi-tool chaining in one turn.
- **Safety** — read-only Postgres role enforced at the DB; SQL parsed to an AST (not string-matched);
  statement timeout; row cap; artifact bounds; prompt-injection defenses. See §6.
- **Streaming** — real SSE of the *stages* (reasoning → tool + args → progress → result → prose),
  with mid-stream disconnect handling and heartbeats.
- **Provider abstraction** — Groq by default, selectable by env. See §5.
- **Data foundation** — idempotent load, FK'd schema, time-bucket indexes, documented inconsistencies.
- **API** — async (asyncpg behind `async def`), an in-DB time-series aggregate, a consistent error
  envelope, a meaningful `/health`.
- **Frontend** — data table, chart, streaming chat, and a **persistent, re-runnable pinned
  dashboard**; loading / empty / error / dead-stream / 500 states.
- **Ship** — one-command compose, multi-stage non-root images, healthchecks, `.env.example`, a
  trace-ID that follows a request through API → agent → tool → SQL.

**Consciously simplified (not cut, but scoped):**

- Charts are **specs, not server-rendered images** — the frontend draws them, and the spec carries
  its SQL so a pinned chart re-runs instead of being a dead PNG. PowerPoint uses python-pptx *native*
  charts, so there's no image-rendering dependency anywhere.
- The `query` plugin has the **model write SQL directly** rather than doing a second NL→SQL LLM call
  — one model, and the SQL is visible for streaming and debugging.
- No auth/multi-tenant, no Alembic version history (a single `create_all` + role migration is enough
  for a fresh schema), no data-cleaning pipeline beyond type coercion + documented quirks.

---

## 5. Design decisions & tradeoffs

- **Provider = Groq behind an interface.** The LLM sits behind `LLMProvider` (`app/agent/providers`).
  We chose Groq (`openai/gpt-oss-120b`) because it's a capable, free tool-calling model. **Tradeoff:**
  the free tier is **8,000 tokens/minute**, which is tight. We designed around it: compact system
  prompt, and crucially **the model sees only a preview of a query result (columns + 15 rows +
  row_count), never the full table** — the full result stays server-side for downstream plugins.
  This both fits the budget *and* shrinks the prompt-injection surface. Adding another provider is one
  file implementing `LLMProvider` + a branch in `factory.py`.
- **Two Postgres roles.** The app role owns writable tables (pins); the agent role has `SELECT` on the
  analytics tables only. **We chose DB-enforced least privilege over prompt-based rules** because the
  person in the chat box is assumed hostile — no prompt can widen a grant.
- **SQL guard via AST, not regex.** sqlglot parses the statement; we reject anything that isn't a
  single read, plus schema-probing and dangerous functions. **We chose parsing over string-matching**
  because the brief (correctly) says string-matching for `DROP` is defeatable.
- **Row cap via server-side streaming.** Results are streamed with a cursor and cut at `ROW_CAP`, so a
  query matching millions of rows never materializes in memory.
- **SSE over WebSocket.** The chat only needs server→client streaming; SSE is simpler and
  `request.is_disconnected()` gives clean teardown. **Tradeoff:** no client→server mid-turn messaging
  (not needed here).
- **Simplicity bias throughout.** No repository/DAO layer over SQLAlchemy, no DI container, no state
  library on the frontend. The one real abstraction — the plugin contract — earns its place because
  it removes the `if tool == ...` duplication the brief warns against.

---

## 6. What the agent is defended against — and what's left open

The follow-up call will try to break this, so here's the honest map.

**Defended:**

- **Writes / DDL** — impossible: the agent connects as a role with no write grants and
  `default_transaction_read_only = on`. Even a hand-crafted `INSERT`/`DROP` is denied by Postgres.
- **SQL injection of intent** — the AST guard rejects multi-statement SQL, non-SELECT roots,
  `SELECT ... INTO`, `pg_catalog`/`information_schema` access, and functions like `pg_sleep`,
  `pg_read_file`, `dblink`. (17 adversarial cases covered by tests.)
- **Resource exhaustion** — statement timeout + row cap on queries; row/byte/slide caps on artifacts.
  "Export every message to Excel" returns a `too_large` error, not an OOM.
- **Prompt injection via the data itself** — message content and usernames are framed as untrusted
  data in the system prompt, and, more importantly, **the agent's capabilities are structural, not
  prompt-granted**: the only things it can do are the registered plugins under their schemas and the
  read-only role. No "ignore your rules and DROP TABLE" in a message body can widen that. The model
  also only ever sees a small preview of row content, limiting the injection surface.
- **No secret/file/network surface** — there is no tool that reads env, files, or the network;
  artifact writes are bounded to `ARTIFACT_DIR` with sanitized filenames (no path traversal).
- **Errors are sanitized** before reaching the model or the wire (no DSNs, no stack traces).

**Knowingly left open:**

- We don't semantically scrub message content the model chooses to *quote back*. A crafted message
  can't gain capabilities, but could still influence the phrasing of a reply.
- No per-user rate limiting on chat (single-tenant demo) — a user can burn API tokens.
- The model can write a *semantically wrong-but-safe* SELECT: we guarantee safety, not analytical
  correctness. We explain results but can't certify them.
- The read-only role's grants are table-scoped; a new analytics table would need to be added to the
  grant list in `migrate.py` (by design — deny by default).

---

## 7. What I'd do next (with more time)

- **Streaming-progress inside long queries** — currently a slow query blocks between stage events; I'd
  stream partial reasoning/progress during execution and add a per-tool timeout surfaced as a stage.
- **Result caching + prompt caching** to stretch the free-tier token budget further, and an explicit
  429/back-off UX when the rate limit is hit mid-turn.
- **A second provider implementation** (e.g. another OpenAI-compatible `LLMProvider`) to prove the
  abstraction with a real swap, plus an offline/echo provider baked into a CI test that runs the
  whole loop without credits.
- **Tighter chaining ergonomics** — let a plugin declare nested per-item input refs (e.g. per-slide
  references in `powerpoint`) rather than a flat `input_refs`.
- **More schema-aware SQL help** — feed the model column types and a few example values so it writes
  better SQL on the first try, reducing retries (and tokens).
- **Alembic migrations** if the schema needed to evolve over time; `create_all` is deliberate for a
  fresh, single-schema app.

---

## 8. Project layout

```
backend/
  app/
    main.py                  # app factory, /health, trace-ID middleware, plugin discovery
    config.py                # one Settings (fail-loud), logging.py (structlog + trace id)
    db/        engine.py (app + read-only engines), models.py (schema)
    api/       routes_data / routes_chat / routes_artifacts / routes_pins, errors.py, schemas.py
    services/  analytics.py  # data-access + the in-DB aggregate
    agent/     loop.py, prompt.py, providers/ (base, groq_provider, factory)
    plugins/   base.py (contract), registry.py (discovery), builtin/ (query, chart, excel, powerpoint)
    safety/    sql_guard.py (AST gate), execution.py (RO run + row cap), 
    artifacts.py               # bounded artifact store (temp-write + atomic move)
  scripts/   migrate.py, load_data.py, transforms.py
  tests/     29 tests (sql guard, query, agent loop, chart/excel/pptx chains)
frontend/    React + Vite (Chat, Explore, Dashboard), themed to apcid.netlify.app
docs/        module-by-module design notes + DEVELOPMENT-INSTRUCTIONS.md
data/dataset/  the dataset CSVs (committed, CC0)
```

---

## 9. Notes on the data

- **Grain:** `messages` is the event log (a 5,000-row sample). `daily_stats` / `channel_daily_stats`
  are pre-aggregated per day.
- **Time zones:** timestamps are stored as UTC by convention.
- **Relative dates** ("last month", "after March") resolve against the **latest message timestamp in
  the data** (2026-06-16), not wall-clock — the dataset runs into the future.
- **Handled inconsistencies:** the dataset's `(server_id, user_id)` is not actually unique (52
  collisions), so `members` uses a surrogate key; `daily_stats` member columns are unreliable, so
  activity is computed from `messages`; blanks become NULL; booleans/ints/timestamps are coerced.
```
