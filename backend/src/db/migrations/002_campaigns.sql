-- Autonomous campaigns: a discovery agent finds websites via web search,
-- crawler agents extract leads from them.

CREATE TYPE campaign_status AS ENUM ('queued', 'running', 'completed', 'failed', 'cancelled');
CREATE TYPE source_status AS ENUM ('queued', 'crawling', 'done', 'no_leads', 'blocked', 'failed', 'skipped');

CREATE TABLE campaigns (
  id                  BIGSERIAL PRIMARY KEY,
  name                TEXT NOT NULL,
  professions         profession[] NOT NULL,
  states              indian_state[] NOT NULL,
  cities              TEXT[] NOT NULL DEFAULT '{}',
  max_sites           INTEGER NOT NULL DEFAULT 30 CHECK (max_sites BETWEEN 1 AND 500),
  max_pages_per_site  INTEGER NOT NULL DEFAULT 25 CHECK (max_pages_per_site BETWEEN 1 AND 500),
  status              campaign_status NOT NULL DEFAULT 'queued',
  progress            JSONB NOT NULL DEFAULT '{}'::jsonb,
  error               TEXT,
  worker_id           TEXT,
  created_by          BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at          TIMESTAMPTZ,
  finished_at         TIMESTAMPTZ,
  heartbeat_at        TIMESTAMPTZ
);
CREATE INDEX campaigns_status_idx ON campaigns (status, created_at);

-- Every website the discovery agent has found. Shared across campaigns so the
-- same site isn't re-crawled every time.
CREATE TABLE sources (
  id               BIGSERIAL PRIMARY KEY,
  domain           TEXT UNIQUE NOT NULL,
  url              TEXT NOT NULL,
  title            TEXT,
  discovered_query TEXT,
  campaign_id      BIGINT REFERENCES campaigns(id) ON DELETE SET NULL,
  status           source_status NOT NULL DEFAULT 'queued',
  detail           TEXT,
  pages_crawled    INTEGER NOT NULL DEFAULT 0,
  leads_found      INTEGER NOT NULL DEFAULT 0,
  last_crawled_at  TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sources_campaign_idx ON sources (campaign_id);

ALTER TABLE scrape_runs ADD COLUMN campaign_id BIGINT REFERENCES campaigns(id) ON DELETE SET NULL;
