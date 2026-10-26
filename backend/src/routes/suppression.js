import { Router } from 'express';
import { withTransaction } from '../db/pool.js';
import { authenticate, requirePermission } from '../middleware/auth.js';
import { HttpError, validate } from '../middleware/errors.js';
import { suppressionSchema } from '../schemas.js';
import { audit } from '../services/audit.js';
import { contactHash, normalizeEmail, normalizeIndianMobile } from '../utils/contact.js';

const router = Router();
router.use(authenticate, requirePermission('suppression:manage'));

/**
 * Record an opt-out / erasure request. The contact is hashed into the
 * suppression list (so future scrapes skip it) and any matching lead is deleted.
 */
router.post('/', validate(suppressionSchema), async (req, res, next) => {
  try {
    const email = normalizeEmail(req.body.value);
    const phone = email ? null : normalizeIndianMobile(req.body.value);
    const value = email ?? phone;
    if (!value) throw new HttpError(400, 'Value must be an email address or Indian mobile number');
    const kind = email ? 'email' : 'phone';

    const deleted = await withTransaction(async (db) => {
      await db.query(
        `INSERT INTO suppression_list (value_hash, kind, reason, created_by) VALUES ($1, $2, $3, $4)
         ON CONFLICT (value_hash) DO NOTHING`,
        [contactHash(value), kind, req.body.reason, req.user.id],
      );
      const column = kind === 'email' ? 'email' : 'phone_e164';
      const { rows } = await db.query(`DELETE FROM leads WHERE ${column} = $1 RETURNING id`, [value]);
      await audit(req.user.id, 'suppress', 'contact', null, { kind, leads_deleted: rows.length }, db);
      return rows.length;
    });

    res.status(201).json({ kind, leads_deleted: deleted });
  } catch (err) {
    next(err);
  }
});

export default router;
