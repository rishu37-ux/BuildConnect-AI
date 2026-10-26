import { Router } from 'express';
import bcrypt from 'bcryptjs';
import { query } from '../db/pool.js';
import { authenticate, requirePermission } from '../middleware/auth.js';
import { HttpError, validate } from '../middleware/errors.js';
import { createUserSchema, updateUserSchema } from '../schemas.js';
import { audit } from '../services/audit.js';

const router = Router();
const PUBLIC = 'id, email, full_name, role, is_active, created_at';

router.use(authenticate);

// Lightweight directory so managers can pick an assignee.
router.get('/', requirePermission('users:manage', 'leads:assign'), async (_req, res, next) => {
  try {
    const { rows } = await query(`SELECT ${PUBLIC} FROM users ORDER BY full_name`);
    res.json(rows);
  } catch (err) {
    next(err);
  }
});

router.post('/', requirePermission('users:manage'), validate(createUserSchema), async (req, res, next) => {
  try {
    const { email, full_name, password, role } = req.body;
    const { rows } = await query(
      `INSERT INTO users (email, full_name, password_hash, role) VALUES ($1, $2, $3, $4) RETURNING ${PUBLIC}`,
      [email, full_name, await bcrypt.hash(password, 12), role],
    );
    await audit(req.user.id, 'create', 'user', rows[0].id, { email, role });
    res.status(201).json(rows[0]);
  } catch (err) {
    next(err);
  }
});

router.patch('/:id(\\d+)', requirePermission('users:manage'), validate(updateUserSchema), async (req, res, next) => {
  try {
    const id = Number(req.params.id);
    if (id === req.user.id && (req.body.role && req.body.role !== 'admin' || req.body.is_active === false)) {
      throw new HttpError(400, 'You cannot demote or deactivate your own account');
    }
    const patch = { ...req.body };
    if (patch.password) {
      patch.password_hash = await bcrypt.hash(patch.password, 12);
      delete patch.password;
    }
    const keys = Object.keys(patch);
    if (!keys.length) throw new HttpError(400, 'Nothing to update');
    const { rows } = await query(
      `UPDATE users SET ${keys.map((k, i) => `${k} = $${i + 2}`).join(', ')}, updated_at = now()
       WHERE id = $1 RETURNING ${PUBLIC}`,
      [id, ...keys.map((k) => patch[k])],
    );
    if (!rows[0]) throw new HttpError(404, 'User not found');
    await audit(req.user.id, 'update', 'user', id, { fields: keys.filter((k) => k !== 'password_hash') });
    res.json(rows[0]);
  } catch (err) {
    next(err);
  }
});

export default router;
