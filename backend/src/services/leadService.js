import { query, withTransaction } from '../db/pool.js';
import { contactHash, normalizeEmail, normalizeIndianMobile } from '../utils/contact.js';

export const LEAD_COLUMNS = [
  'id', 'full_name', 'firm_name', 'profession', 'phone_e164', 'email', 'city', 'district',
  'state', 'website', 'status', 'notes', 'assigned_to', 'source_url', 'source_domain',
  'confidence', 'first_seen_at', 'last_seen_at', 'created_at', 'updated_at',
];

const SORTABLE = new Set(['created_at', 'updated_at', 'last_seen_at', 'full_name', 'confidence', 'city']);
const EXPORT_LIMIT = 50_000;

/** Build a WHERE clause from dashboard filters. */
function buildFilters(f) {
  const where = [];
  const params = [];
  const add = (sql, value) => {
    params.push(value);
    where.push(sql.replace('?', `$${params.length}`));
  };
  if (f.q) {
    params.push(f.q);
    const n = `$${params.length}`;
    where.push(`(to_tsvector('simple', coalesce(full_name,'') || ' ' || coalesce(firm_name,'') || ' ' || coalesce(city,''))
                 @@ plainto_tsquery('simple', ${n})
                 OR email ILIKE '%' || ${n} || '%' OR phone_e164 LIKE '%' || ${n} || '%')`);
  }
  if (f.state) add('state = ?', f.state);
  if (f.profession) add('profession = ?', f.profession);
  if (f.status) add('status = ?', f.status);
  if (f.city) add('city ILIKE ?', f.city);
  if (f.assignedTo === 'unassigned') where.push('assigned_to IS NULL');
  else if (f.assignedTo) add('assigned_to = ?', Number(f.assignedTo));
  if (f.hasPhone) where.push('phone_e164 IS NOT NULL');
  if (f.hasEmail) where.push('email IS NOT NULL');
  return { clause: where.length ? `WHERE ${where.join(' AND ')}` : '', params };
}

export async function listLeads(f) {
  const { clause, params } = buildFilters(f);
  const sort = SORTABLE.has(f.sort) ? f.sort : 'created_at';
  const dir = f.order === 'asc' ? 'ASC' : 'DESC';
  const offset = (f.page - 1) * f.pageSize;

  const [rows, total] = await Promise.all([
    query(
      `SELECT ${LEAD_COLUMNS.join(', ')} FROM leads ${clause}
       ORDER BY ${sort} ${dir}, id DESC LIMIT ${f.pageSize} OFFSET ${offset}`,
      params,
    ),
    query(`SELECT count(*)::int AS n FROM leads ${clause}`, params),
  ]);
  return { data: rows.rows, page: f.page, pageSize: f.pageSize, total: total.rows[0].n };
}

export async function exportLeads(f) {
  const { clause, params } = buildFilters(f);
  const { rows } = await query(
    `SELECT ${LEAD_COLUMNS.join(', ')} FROM leads ${clause} ORDER BY created_at DESC LIMIT ${EXPORT_LIMIT}`,
    params,
  );
  return rows;
}

export async function getLead(id) {
  const { rows } = await query(`SELECT ${LEAD_COLUMNS.join(', ')} FROM leads WHERE id = $1`, [id]);
  return rows[0] ?? null;
}

export async function updateLead(id, patch) {
  const fields = Object.keys(patch);
  if (!fields.length) return getLead(id);
  const sets = fields.map((k, i) => `${k} = $${i + 2}`);
  const { rows } = await query(
    `UPDATE leads SET ${sets.join(', ')}, updated_at = now() WHERE id = $1 RETURNING ${LEAD_COLUMNS.join(', ')}`,
    [id, ...fields.map((k) => patch[k])],
  );
  return rows[0] ?? null;
}

export async function deleteLead(id) {
  const { rowCount } = await query('DELETE FROM leads WHERE id = $1', [id]);
  return rowCount > 0;
}

export async function getStats() {
  const [totals, byState, byProfession, byStatus] = await Promise.all([
    query(`SELECT
             count(*)::int AS total,
             count(*) FILTER (WHERE created_at > now() - interval '7 days')::int AS last_7_days,
             count(phone_e164)::int AS with_phone,
             count(email)::int AS with_email
           FROM leads`),
    query('SELECT state AS k, count(*)::int AS n FROM leads GROUP BY state'),
    query('SELECT profession AS k, count(*)::int AS n FROM leads GROUP BY profession'),
    query('SELECT status AS k, count(*)::int AS n FROM leads GROUP BY status'),
  ]);
  const toMap = (r) => Object.fromEntries(r.rows.map((row) => [row.k, row.n]));
  return {
    ...totals.rows[0],
    by_state: toMap(byState),
    by_profession: toMap(byProfession),
    by_status: toMap(byStatus),
  };
}

async function isSuppressed(db, phone, email) {
  const hashes = [phone, email].filter(Boolean).map(contactHash);
  if (!hashes.length) return false;
  const { rowCount } = await db.query('SELECT 1 FROM suppression_list WHERE value_hash = ANY($1)', [hashes]);
  return rowCount > 0;
}

/**
 * Insert or merge a batch of scraped leads. Leads are deduplicated on phone
 * and email; existing records only have empty fields filled in, so manual
 * edits by the sales team are never overwritten by a later scrape.
 */
export async function ingestLeads(leads, scrapeRunId) {
  const result = { inserted: 0, merged: 0, suppressed: 0, invalid: 0 };

  await withTransaction(async (db) => {
    for (const lead of leads) {
      const phone = normalizeIndianMobile(lead.phone);
      const email = normalizeEmail(lead.email);
      if (!phone && !email) {
        result.invalid += 1;
        continue;
      }
      if (await isSuppressed(db, phone, email)) {
        result.suppressed += 1;
        continue;
      }

      const sourceDomain = new URL(lead.source_url).hostname;
      const { rows: matches } = await db.query(
        'SELECT id, phone_e164, email FROM leads WHERE phone_e164 = $1 OR email = $2 FOR UPDATE',
        [phone, email],
      );

      if (matches.length === 0) {
        await db.query(
          `INSERT INTO leads (full_name, firm_name, profession, phone_e164, email, city, district, state,
                              website, source_url, source_domain, scrape_run_id, confidence)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)`,
          [lead.full_name, lead.firm_name, lead.profession, phone, email, lead.city, lead.district,
            lead.state, lead.website, lead.source_url, sourceDomain, scrapeRunId ?? null, lead.confidence],
        );
        result.inserted += 1;
        continue;
      }

      // If phone and email point at two different existing leads, don't try
      // to merge contact fields (it would violate the unique indexes).
      const target = matches[0];
      const canMergeContacts = matches.length === 1;
      await db.query(
        `UPDATE leads SET
           phone_e164 = CASE WHEN $2 THEN coalesce(phone_e164, $3) ELSE phone_e164 END,
           email      = CASE WHEN $2 THEN coalesce(email, $4) ELSE email END,
           firm_name  = coalesce(firm_name, $5),
           city       = coalesce(city, $6),
           district   = coalesce(district, $7),
           website    = coalesce(website, $8),
           state      = CASE WHEN state = 'other' THEN $9::indian_state ELSE state END,
           profession = CASE WHEN profession = 'other' THEN $10::profession ELSE profession END,
           confidence = greatest(confidence, $11),
           last_seen_at = now(),
           updated_at = now()
         WHERE id = $1`,
        [target.id, canMergeContacts, phone, email, lead.firm_name, lead.city, lead.district,
          lead.website, lead.state, lead.profession, lead.confidence],
      );
      result.merged += 1;
    }
  });

  return result;
}
