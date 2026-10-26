# BuildConnect AI

Agentic lead discovery and management for the construction sector:
**architects, structural engineers and contractors in Punjab and Himachal Pradesh**
(plus Chandigarh/Tricity).

```
┌──────────────────────┐   POST /api/ingest   ┌──────────────────────┐   REST + JWT   ┌──────────────────────┐
│  scraper/ (Python)   │ ───────────────────▶ │  backend/ (Node.js)  │ ◀────────────▶ │  frontend/ (React)   │
│  agentic crawler     │   x-api-key auth     │  Express + Postgres  │                │  Vite + Tailwind     │
│  proxy rotation      │                      │  RBAC, dedupe, audit │                │  dashboard + export  │
└──────────────────────┘                      └──────────────────────┘                └──────────────────────┘
```

| Path | What it is |
|---|---|
| `scraper/` | Python 3.11+ async agent: priority-frontier crawl, link scoring, extraction of names, Indian mobiles and emails, profession and location classification, health-aware proxy rotation, robots.txt and rate limiting |
| `backend/` | Node 20+ / Express API on PostgreSQL: JWT auth, role-based access control, lead dedupe/merge, filtering and search, CSV export, opt-out suppression list, audit log |
| `frontend/` | React 18 + Vite + Tailwind CSS v4 dashboard: stats, filters, search, lead detail/edit drawer, assignment, CSV export, opt-out requests |
| `docs/COMPLIANCE.md` | Data protection controls (DPDP Act 2023), source selection, and why CAPTCHAs are not bypassed |

## Quick start

```bash
cp .env.example .env          # then change the secrets
docker compose up -d db backend frontend
docker compose exec backend node src/db/seed.js   # create the admin user from SEED_ADMIN_*
open http://localhost:5173
```

Run a crawl (put seed URLs in `scraper/seeds.example.txt` or pass `--seed`):

```bash
docker compose run --rm scraper --seed https://firm-or-directory.example/architects --max-pages 100
```

### Local development without Docker

```bash
# Backend
cd backend && npm install
export DATABASE_URL=postgres://buildconnect:buildconnect@localhost:5432/buildconnect \
       JWT_SECRET=dev INGEST_API_KEY=dev-ingest SEED_ADMIN_PASSWORD='ChangeMe123!'
npm run migrate && npm run seed && npm run dev

# Frontend
cd frontend && npm install && npm run dev        # http://localhost:5173

# Scraper
cd scraper && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
BC_INGEST_API_KEY=dev-ingest python -m buildconnect_scraper --seed https://example.in/members \
    --profession architect --state punjab --max-pages 50
# or review results locally first:
python -m buildconnect_scraper --seeds-file seeds.txt --dry-run out/leads.jsonl
```

## Scraper: how the agent works

`scraper/buildconnect_scraper/agent.py` runs an **observe → extract → decide** loop:

1. **Observe**: `Fetcher` fetches the highest-priority URL from the frontier through
   the `ProxyPool`, after checking robots.txt and waiting for the domain's rate-limit slot.
2. **Extract**: `extractors.py` finds schema.org JSON-LD entities and directory-style
   "cards" (the smallest DOM block holding a name and a contact). It normalises
   mobiles to `+91XXXXXXXXXX`, de-obfuscates `name [at] firm [dot] in` emails,
   classifies the profession (`Ar.`, `Er.`, "structural consultant", "contractor"…),
   maps the location to a district via the Punjab/HP gazetteer, and scores confidence.
   Leads outside the target professions or states are dropped.
3. **Decide**: every outgoing link is scored by the goal's vocabulary, place names,
   listing/pagination cues, and what has worked this run: URL path patterns and
   domains that produced leads are boosted, domains with no yield after N pages
   are abandoned, and domains that serve a CAPTCHA or block are dropped.

Leads are pushed in batches to `POST /api/ingest/leads`, where the backend
dedupes on phone and email, fills in missing fields on existing records
(without overwriting edits made by the sales team), and skips suppressed contacts.

**Proxies:** set `BC_PROXIES=http://user:pass@host1:port,http://host2:port`.
Failing proxies get an exponential cooldown, and credentials never appear in logs.

**CAPTCHAs:** these are detected and respected, not solved. See
[docs/COMPLIANCE.md](docs/COMPLIANCE.md).

## Backend API

All routes are under `/api`. User routes take `Authorization: Bearer <jwt>`;
ingest routes take `x-api-key: $INGEST_API_KEY`.

| Method | Route | Permission |
|---|---|---|
| POST | `/auth/login` | public (rate limited) |
| GET | `/auth/me` | any user |
| GET | `/leads?q=&state=&profession=&status=&assignedTo=&hasPhone=&hasEmail=&sort=&order=&page=&pageSize=` | `leads:read` |
| GET | `/leads/stats` | `leads:read` |
| GET | `/leads/export?…same filters` (CSV) | `leads:export` |
| GET / PATCH / DELETE | `/leads/:id` | `leads:read` / `leads:write` (or `leads:write:own`) / `leads:delete` |
| GET / POST / PATCH | `/users`, `/users/:id` | `users:manage` (list also `leads:assign`) |
| POST | `/suppression` | `suppression:manage` |
| GET | `/runs` | `runs:read` |
| POST / PATCH | `/ingest/runs`, `/ingest/runs/:id` | ingest key |
| POST | `/ingest/leads` | ingest key |

### Roles

| Permission | admin | manager | sales | viewer |
|---|:-:|:-:|:-:|:-:|
| View leads | ✓ | ✓ | ✓ | ✓ |
| Edit leads | ✓ | ✓ | own assigned only | |
| Assign leads, export CSV, opt-outs, view runs | ✓ | ✓ | | |
| Delete leads, manage users, audit log | ✓ | | | |

## Tests

```bash
cd backend && TEST_DATABASE_URL=postgres://…/buildconnect_test npm test   # unit + API integration (DB is wiped)
cd scraper && python -m pytest -q                                         # extractors, proxy pool, fetcher, agent
cd frontend && npm run build
```

CI (`.github/workflows/ci.yml`) runs all three on every push.

## Repository layout

```
backend/
  src/app.js, index.js, config.js, schemas.js
  src/db/          pool, migrate, seed, migrations/001_init.sql
  src/middleware/  auth (JWT + RBAC + ingest key), errors/validation
  src/routes/      auth, users, leads, ingest (+runs), suppression
  src/services/    leadService (dedupe/merge/filter/export), audit
  src/utils/       contact normalisation, CSV
scraper/buildconnect_scraper/
  agent.py         LeadAgent: frontier, link scoring, adaptive domain/path learning
  fetcher.py       retries, proxy rotation, challenge detection
  proxy.py         health-aware ProxyPool
  politeness.py    robots.txt cache, per-domain rate limiter
  extractors.py    JSON-LD + card extraction, phone/email/profession
  geo.py           Punjab / Himachal Pradesh district gazetteer
  sink.py          API sink (batched) and JSONL dry-run sink
  cli.py           command-line entry point
frontend/src/
  pages/           Login, Dashboard
  components/      StatCards, Filters, LeadTable, LeadDrawer, Pagination, SuppressDialog
  lib/             api client, auth context, labels
```
