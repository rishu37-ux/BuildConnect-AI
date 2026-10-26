import { Router } from 'express';
import { query } from '../db/pool.js';
import { authenticate, requireIngestKey, requirePermission } from '../middleware/auth.js';
import { HttpError, validate } from '../middleware/errors.js';
import {
  campaignUpdateSchema, claimCampaignSchema, finishRunSchema, ingestBatchSchema, registerSourcesSchema,
  sourceUpdateSchema, startRunSchema,
} from '../schemas.js';
import * as campaigns from '../services/campaignService.js';
import { ingestLeads } from '../services/leadService.js';

/** Machine endpoints used by the Python scraper (API-key auth). */
export const ingestRouter = Router();
ingestRouter.use(requireIngestKey);

ingestRouter.post('/runs', validate(startRunSchema), async (req, res, next) => {
  try {
    const { rows } = await query(
      'INSERT INTO scrape_runs (agent_name, target, campaign_id) VALUES ($1, $2, $3) RETURNING *',
      [req.body.agent_name, req.body.target, req.body.campaign_id ?? null],
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

// --- campaign worker protocol ---------------------------------------------

ingestRouter.post('/campaigns/claim', validate(claimCampaignSchema), async (req, res, next) => {
  try {
    const campaign = await campaigns.claimCampaign(req.body.worker_id);
    if (!campaign) return res.status(204).end();
    res.json(campaign);
  } catch (err) {
    next(err);
  }
});

ingestRouter.patch('/campaigns/:id(\\d+)', validate(campaignUpdateSchema), async (req, res, next) => {
  try {
    const result = await campaigns.reportCampaign(Number(req.params.id), req.body);
    if (!result) throw new HttpError(404, 'Campaign not found');
    res.json(result);
  } catch (err) {
    next(err);
  }
});

ingestRouter.post('/campaigns/:id(\\d+)/sources', validate(registerSourcesSchema), async (req, res, next) => {
  try {
    res.json(await campaigns.registerSources(Number(req.params.id), req.body.sources, req.body.recrawl_after_days));
  } catch (err) {
    next(err);
  }
});

ingestRouter.patch('/sources/:id(\\d+)', validate(sourceUpdateSchema), async (req, res, next) => {
  try {
    const source = await campaigns.updateSource(Number(req.params.id), req.body);
    if (!source) throw new HttpError(404, 'Source not found');
    res.json(source);
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
