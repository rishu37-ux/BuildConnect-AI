import crypto from 'node:crypto';
import jwt from 'jsonwebtoken';
import { config } from '../config.js';
import { HttpError } from './errors.js';

/**
 * Role → permission map. Keep this the single source of truth for RBAC;
 * routes ask for a permission, never for a role.
 */
export const PERMISSIONS = {
  admin: ['leads:read', 'leads:write', 'leads:delete', 'leads:export', 'leads:assign',
    'users:manage', 'suppression:manage', 'runs:read', 'campaigns:manage', 'audit:read'],
  manager: ['leads:read', 'leads:write', 'leads:export', 'leads:assign',
    'suppression:manage', 'runs:read', 'campaigns:manage'],
  sales: ['leads:read', 'leads:write:own'],
  viewer: ['leads:read'],
};

export function hasPermission(role, permission) {
  return (PERMISSIONS[role] ?? []).includes(permission);
}

export function signToken(user) {
  return jwt.sign({ sub: user.id, role: user.role, email: user.email }, config.jwtSecret, {
    expiresIn: config.jwtExpiresIn,
  });
}

export function authenticate(req, _res, next) {
  const header = req.get('authorization') ?? '';
  const [scheme, token] = header.split(' ');
  if (scheme !== 'Bearer' || !token) return next(new HttpError(401, 'Authentication required'));
  try {
    const payload = jwt.verify(token, config.jwtSecret);
    req.user = { id: Number(payload.sub), role: payload.role, email: payload.email };
    next();
  } catch {
    next(new HttpError(401, 'Invalid or expired token'));
  }
}

/** Require at least one of the given permissions. */
export function requirePermission(...permissions) {
  return (req, _res, next) => {
    if (!req.user) return next(new HttpError(401, 'Authentication required'));
    if (permissions.some((p) => hasPermission(req.user.role, p))) return next();
    next(new HttpError(403, 'Insufficient permissions'));
  };
}

/** Machine-to-machine auth for the scraper's ingest endpoint. */
export function requireIngestKey(req, _res, next) {
  const provided = Buffer.from(req.get('x-api-key') ?? '');
  const expected = Buffer.from(config.ingestApiKey);
  if (provided.length === expected.length && crypto.timingSafeEqual(provided, expected)) return next();
  next(new HttpError(401, 'Invalid ingest API key'));
}
