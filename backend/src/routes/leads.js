import { Router } from 'express';
import { authenticate, hasPermission, requirePermission } from '../middleware/auth.js';
import { HttpError, validate } from '../middleware/errors.js';
import { leadFilterSchema, updateLeadSchema } from '../schemas.js';
import { audit } from '../services/audit.js';
import * as leads from '../services/leadService.js';
import { toCsv } from '../utils/csv.js';

const router = Router();
router.use(authenticate);

router.get('/', requirePermission('leads:read'), validate(leadFilterSchema, 'query'), async (req, res, next) => {
  try {
    res.json(await leads.listLeads(req.validatedQuery));
  } catch (err) {
    next(err);
  }
});

router.get('/stats', requirePermission('leads:read'), async (_req, res, next) => {
  try {
    res.json(await leads.getStats());
  } catch (err) {
    next(err);
  }
});

router.get('/export', requirePermission('leads:export'), validate(leadFilterSchema, 'query'), async (req, res, next) => {
  try {
    const rows = await leads.exportLeads(req.validatedQuery);
    const { page: _p, pageSize: _ps, ...filters } = req.validatedQuery;
    await audit(req.user.id, 'export', 'lead', null, { count: rows.length, filters });
    const stamp = new Date().toISOString().slice(0, 10);
    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="buildconnect-leads-${stamp}.csv"`);
    res.send(toCsv(rows, leads.LEAD_COLUMNS));
  } catch (err) {
    next(err);
  }
});

router.get('/:id(\\d+)', requirePermission('leads:read'), async (req, res, next) => {
  try {
    const lead = await leads.getLead(Number(req.params.id));
    if (!lead) throw new HttpError(404, 'Lead not found');
    res.json(lead);
  } catch (err) {
    next(err);
  }
});

router.patch('/:id(\\d+)', requirePermission('leads:write', 'leads:write:own'), validate(updateLeadSchema),
  async (req, res, next) => {
    try {
      const id = Number(req.params.id);
      const existing = await leads.getLead(id);
      if (!existing) throw new HttpError(404, 'Lead not found');

      // Sales users may only edit leads assigned to them.
      if (!hasPermission(req.user.role, 'leads:write') && existing.assigned_to !== req.user.id) {
        throw new HttpError(403, 'You can only edit leads assigned to you');
      }
      if ('assigned_to' in req.body && !hasPermission(req.user.role, 'leads:assign')) {
        throw new HttpError(403, 'You cannot reassign leads');
      }

      const updated = await leads.updateLead(id, req.body);
      await audit(req.user.id, 'update', 'lead', id, { fields: Object.keys(req.body) });
      res.json(updated);
    } catch (err) {
      next(err);
    }
  });

router.delete('/:id(\\d+)', requirePermission('leads:delete'), async (req, res, next) => {
  try {
    const id = Number(req.params.id);
    if (!(await leads.deleteLead(id))) throw new HttpError(404, 'Lead not found');
    await audit(req.user.id, 'delete', 'lead', id);
    res.status(204).end();
  } catch (err) {
    next(err);
  }
});

export default router;
