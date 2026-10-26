-- Core schema for BuildConnect AI

CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE user_role AS ENUM ('admin', 'manager', 'sales', 'viewer');
CREATE TYPE profession AS ENUM ('architect', 'structural_engineer', 'contractor', 'other');
CREATE TYPE lead_status AS ENUM ('new', 'contacted', 'qualified', 'converted', 'rejected');
CREATE TYPE indian_state AS ENUM ('punjab', 'himachal_pradesh', 'chandigarh', 'other');

CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  email         CITEXT UNIQUE NOT NULL,
  full_name     TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role          user_role NOT NULL DEFAULT 'viewer',
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scrape_runs (
  id            BIGSERIAL PRIMARY KEY,
  agent_name    TEXT NOT NULL,
  target        JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ,
  pages_fetched INTEGER NOT NULL DEFAULT 0,
  leads_found   INTEGER NOT NULL DEFAULT 0,
  stats         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE leads (
  id              BIGSERIAL PRIMARY KEY,
  full_name       TEXT NOT NULL,
  firm_name       TEXT,
  profession      profession NOT NULL DEFAULT 'other',
  phone_e164      TEXT,
  email           CITEXT,
  city            TEXT,
  district        TEXT,
  state           indian_state NOT NULL DEFAULT 'other',
  website         TEXT,
  status          lead_status NOT NULL DEFAULT 'new',
  notes           TEXT,
  assigned_to     BIGINT REFERENCES users(id) ON DELETE SET NULL,
  -- Provenance: where and when the contact was published.
  source_url      TEXT NOT NULL,
  source_domain   TEXT NOT NULL,
  scrape_run_id   BIGINT REFERENCES scrape_runs(id) ON DELETE SET NULL,
  confidence      REAL NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
  first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT lead_has_contact CHECK (phone_e164 IS NOT NULL OR email IS NOT NULL)
);

-- Dedupe keys: one lead per phone and per email.
CREATE UNIQUE INDEX leads_phone_uniq ON leads (phone_e164) WHERE phone_e164 IS NOT NULL;
CREATE UNIQUE INDEX leads_email_uniq ON leads (email) WHERE email IS NOT NULL;
CREATE INDEX leads_filter_idx ON leads (state, profession, status);
CREATE INDEX leads_assigned_idx ON leads (assigned_to);
CREATE INDEX leads_search_idx ON leads
  USING gin (to_tsvector('simple', coalesce(full_name,'') || ' ' || coalesce(firm_name,'') || ' ' || coalesce(city,'')));

-- Opt-out / do-not-contact list (DPDP Act 2023). Values are stored as SHA-256
-- hashes so the list itself doesn't retain the personal data.
CREATE TABLE suppression_list (
  id          BIGSERIAL PRIMARY KEY,
  value_hash  TEXT UNIQUE NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('phone', 'email')),
  reason      TEXT,
  created_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
  action      TEXT NOT NULL,
  entity      TEXT NOT NULL,
  entity_id   TEXT,
  details     JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_entity_idx ON audit_log (entity, entity_id);
