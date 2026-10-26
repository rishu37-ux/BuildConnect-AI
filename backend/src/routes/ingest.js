import { Router } from 'express';
import { query } from '../db/pool.js';
import { authenticate, requireIngestKey, requirePermission } from '../middleware/auth.js';
import { HttpError, validate } from '../middleware/errors.js';
import { finishRunSchema, ingestBatchSchema, startRunSchema } from '../schemas.js';
import { ingestLeads } from '../services/leadService.js';

/** Machine endpoints used by the Python scraper (API-key auth). */
export const ingestRouter = Router();
ingestRouter.use(requireIngestKey);

ingestRouter.post('/runs', validate(startRunSchema), async (req, res, next) => {
  try {
    const { rows } = await query(
      'INSERT INTO scrape_runs (agent_name, target) VALUES ($1, $2) RETURNING *',
      [req.body.agent_name, req.body.target],
    );
    res.status(201).json(rows[0]);
  } catch (err) {
    next(err);
  }
});

ingestRouter.patch('/runs/:id(\\d+)', validate(finishRunSchema), async (req, res, next) => {
  try {
    const { rows } = await query(
      `UPDATE scrape_runs SET finished_at = now(), pages_fetched = $2, leads_found = $3, stats = $4
       WHERE id = $1 RETURNING *`,
      [Number(req.params.id), req.body.pages_fetched, req.body.leads_found, req.body.stats],
    );
    if (!rows[0]) throw new HttpError(404, 'Run not found');
    res.json(rows[0]);
  } catch (err) {
    next(err);
  }
});

ingestRouter.post('/leads', validate(ingestBatchSchema), async (req, res, next) => {
  try {
    res.json(await ingestLeads(req.body.leads, req.body.run_id));
  } catch (err) {
    next(err);
  }
});

/** Dashboard view of scrape runs (user auth). */
export const runsRouter = Router();
runsRouter.get('/', authenticate, requirePermission('runs:read'), async (_req, res, next) => {
  try {
    const { rows } = await query('SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 100');
    res.json(rows);
  } catch (err) {
    next(err);
  }
});
