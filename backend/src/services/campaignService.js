import { query, withTransaction } from '../db/pool.js';

// node-postgres doesn't parse arrays of custom enum types, so cast them to text[].
const CAMPAIGN_COLUMNS = `id, name, professions::text[] AS professions, states::text[] AS states, cities,
  max_sites, max_pages_per_site, status, progress, error, worker_id, created_by, created_at, started_at,
  finished_at, heartbeat_at`;

// A running campaign whose worker hasn't reported for this long is re-queued.
const STALE_AFTER = '10 minutes';

/** Atomically hand the oldest queued (or abandoned) campaign to a worker. */
export async function claimCampaign(workerId) {
  const { rows } = await query(
    `UPDATE campaigns SET status = 'running', worker_id = $1, heartbeat_at = now(),
            started_at = coalesce(started_at, now())
     WHERE id = (
       SELECT id FROM campaigns
       WHERE status = 'queued' OR (status = 'running' AND heartbeat_at < now() - interval '${STALE_AFTER}')
       ORDER BY created_at
       FOR UPDATE SKIP LOCKED
       LIMIT 1)
     RETURNING ${CAMPAIGN_COLUMNS}`,
    [workerId],
  );
  return rows[0] ?? null;
}

/**
 * Worker progress / completion report. Returns the campaign's current status so
 * the worker learns about a cancellation on its next heartbeat.
 */
export async function reportCampaign(id, { progress, status, error }) {
  const { rows } = await query(
    `UPDATE campaigns SET
       progress     = CASE WHEN $2::jsonb IS NULL THEN progress ELSE $2::jsonb END,
       status       = CASE WHEN status = 'running' AND $3::text IS NOT NULL THEN $3::text::campaign_status ELSE status END,
       error        = coalesce($4, error),
       finished_at  = CASE WHEN $3::text IS NOT NULL OR status = 'cancelled' THEN coalesce(finished_at, now()) ELSE finished_at END,
       heartbeat_at = now()
     WHERE id = $1
     RETURNING id, status`,
    [id, progress ?? null, status ?? null, error ?? null],
  );
  return rows[0] ?? null;
}

/**
 * Record sites found by the discovery agent. New sites, and sites not crawled
 * within `recrawlAfterDays`, are queued for this campaign; the rest are skipped.
 */
export async function registerSources(campaignId, sources, recrawlAfterDays) {
  return withTransaction(async (db) => {
    const out = [];
    for (const s of sources) {
      const domain = new URL(s.url).hostname.toLowerCase().replace(/^www\./, '');
      const { rows } = await db.query(
        `INSERT INTO sources (domain, url, title, discovered_query, campaign_id)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT (domain) DO UPDATE SET
           campaign_id = EXCLUDED.campaign_id, url = EXCLUDED.url,
           title = coalesce(EXCLUDED.title, sources.title),
           discovered_query = EXCLUDED.discovered_query, status = 'queued', detail = NULL
         WHERE sources.status NOT IN ('crawling', 'blocked')
           AND (sources.last_crawled_at IS NULL OR sources.last_crawled_at < now() - make_interval(days => $6))
         RETURNING id, domain, url`,
        [domain, s.url, s.title ?? null, s.query ?? null, campaignId, recrawlAfterDays],
      );
      out.push(rows[0] ? { ...rows[0], status: 'queued' } : { domain, url: s.url, status: 'skipped' });
    }
    return out;
  });
}

export async function updateSource(id, { status, detail, pages_crawled, leads_found }) {
  const terminal = status !== 'crawling';
  const { rows } = await query(
    `UPDATE sources SET status = $2, detail = $3,
       pages_crawled = coalesce($4, pages_crawled), leads_found = coalesce($5, leads_found),
       last_crawled_at = CASE WHEN $6 THEN now() ELSE last_crawled_at END
     WHERE id = $1 RETURNING *`,
    [id, status, detail ?? null, pages_crawled ?? null, leads_found ?? null, terminal],
  );
  return rows[0] ?? null;
}

export async function listCampaigns() {
  const { rows } = await query(
    `SELECT c.*, u.full_name AS created_by_name,
            (SELECT count(*)::int FROM sources s WHERE s.campaign_id = c.id) AS source_count
     FROM (SELECT ${CAMPAIGN_COLUMNS} FROM campaigns) c LEFT JOIN users u ON u.id = c.created_by
     ORDER BY c.created_at DESC LIMIT 100`,
  );
  return rows;
}

export async function createCampaign(c, userId) {
  const { rows } = await query(
    `INSERT INTO campaigns (name, professions, states, cities, max_sites, max_pages_per_site, created_by)
     VALUES ($1, $2::profession[], $3::indian_state[], $4, $5, $6, $7) RETURNING ${CAMPAIGN_COLUMNS}`,
    [c.name, c.professions, c.states, c.cities, c.max_sites, c.max_pages_per_site, userId],
  );
  return rows[0];
}

export async function cancelCampaign(id) {
  const { rows } = await query(
    `UPDATE campaigns SET status = 'cancelled',
       finished_at = CASE WHEN status = 'queued' THEN now() ELSE finished_at END
     WHERE id = $1 AND status IN ('queued', 'running') RETURNING ${CAMPAIGN_COLUMNS}`,
    [id],
  );
  return rows[0] ?? null;
}

export async function campaignSources(id) {
  const { rows } = await query(
    `SELECT id, domain, url, title, discovered_query, status, detail, pages_crawled, leads_found, last_crawled_at
     FROM sources WHERE campaign_id = $1 ORDER BY leads_found DESC, domain`,
    [id],
  );
  return rows;
}
