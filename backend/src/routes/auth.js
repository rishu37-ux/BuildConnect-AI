import { Router } from 'express';
import bcrypt from 'bcryptjs';
import rateLimit from 'express-rate-limit';
import { query } from '../db/pool.js';
import { authenticate, PERMISSIONS, signToken } from '../middleware/auth.js';
import { HttpError, validate } from '../middleware/errors.js';
import { loginSchema } from '../schemas.js';

const router = Router();
const loginLimiter = rateLimit({ windowMs: 15 * 60 * 1000, limit: 20, standardHeaders: true, legacyHeaders: false });

router.post('/login', loginLimiter, validate(loginSchema), async (req, res, next) => {
  try {
    const { rows } = await query(
      'SELECT id, email, full_name, role, password_hash, is_active FROM users WHERE email = $1',
      [req.body.email],
    );
    const user = rows[0];
    const ok = user && user.is_active && (await bcrypt.compare(req.body.password, user.password_hash));
    if (!ok) throw new HttpError(401, 'Invalid email or password');
    const { password_hash: _ph, ...publicUser } = user;
    res.json({ token: signToken(user), user: { ...publicUser, permissions: PERMISSIONS[user.role] } });
  } catch (err) {
    next(err);
  }
});

router.get('/me', authenticate, async (req, res, next) => {
  try {
    const { rows } = await query(
      'SELECT id, email, full_name, role, is_active FROM users WHERE id = $1',
      [req.user.id],
    );
    if (!rows[0]?.is_active) throw new HttpError(401, 'Account disabled');
    res.json({ ...rows[0], permissions: PERMISSIONS[rows[0].role] });
  } catch (err) {
    next(err);
  }
});

export default router;
