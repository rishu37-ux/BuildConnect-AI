import crypto from 'node:crypto';

/**
 * Normalise an Indian mobile number to E.164 (+91XXXXXXXXXX).
 * Accepts "+91 98765 43210", "098765-43210", "9876543210", etc.
 * Returns null for anything that isn't a valid Indian mobile (starts 6-9).
 */
export function normalizeIndianMobile(raw) {
  if (!raw) return null;
  let digits = String(raw).replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);
  return /^[6-9]\d{9}$/.test(digits) ? `+91${digits}` : null;
}

export function normalizeEmail(raw) {
  if (!raw) return null;
  const email = String(raw).trim().toLowerCase();
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) ? email : null;
}

/** Hash used for the suppression list, so opt-outs don't retain raw contact data. */
export function contactHash(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}
