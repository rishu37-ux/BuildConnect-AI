import { query } from '../db/pool.js';

export function audit(userId, action, entity, entityId, details = {}, db = { query }) {
  return db.query(
    'INSERT INTO audit_log (user_id, action, entity, entity_id, details) VALUES ($1, $2, $3, $4, $5)',
    [userId ?? null, action, entity, entityId === undefined ? null : String(entityId), details],
  );
}
