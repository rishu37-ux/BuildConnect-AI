import bcrypt from 'bcryptjs';
import { pool } from './pool.js';

const email = process.env.SEED_ADMIN_EMAIL ?? 'admin@buildconnect.local';
const password = process.env.SEED_ADMIN_PASSWORD;

if (!password) {
  console.error('Set SEED_ADMIN_PASSWORD to create the bootstrap admin.');
  process.exit(1);
}

const hash = await bcrypt.hash(password, 12);
await pool.query(
  `INSERT INTO users (email, full_name, password_hash, role)
   VALUES ($1, 'Administrator', $2, 'admin')
   ON CONFLICT (email) DO NOTHING`,
  [email, hash],
);
console.log(`admin user ready: ${email}`);
await pool.end();
