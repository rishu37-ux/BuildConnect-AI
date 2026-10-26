import { Router } from 'express';
import { authenticate, requirePermission } from '../middleware/auth.js';
import { HttpError, validate } from '../middleware/errors.js';
import { createCampaignSchema } from '../schemas.js';
import { audit } from '../services/audit.js';
import * as campaigns from '../services/campaignService.js';

const router = Router();
router.use(authenticate);

router.get('/', requirePermission('runs:read'), async (_req, res, next) => {
  try {
    res.json(await campaigns.listCampaigns());
  } catch (err) {
    next(err);
  }
});

router.post('/', requirePermission('campaigns:manage'), validate(createCampaignSchema), async (req, res, next) => {
  try {
    const campaign = await campaigns.createCampaign(req.body, req.user.id);
    await audit(req.user.id, 'create', 'campaign', campaign.id, { name: campaign.name });
    res.status(201).json(campaign);
  } catch (err) {
    next(err);
  }
});

router.get('/:id(\\d+)/sources', requirePermission('runs:read'), async (req, res, next) => {
  try {
    res.json(await campaigns.campaignSources(Number(req.params.id)));
  } catch (err) {
    next(err);
  }
});

router.post('/:id(\\d+)/cancel', requirePermission('campaigns:manage'), async (req, res, next) => {
  try {
    const campaign = await campaigns.cancelCampaign(Number(req.params.id));
    if (!campaign) throw new HttpError(409, 'Only queued or running campaigns can be cancelled');
    await audit(req.user.id, 'cancel', 'campaign', campaign.id);
    res.json(campaign);
  } catch (err) {
    next(err);
  }
});

export default router;
