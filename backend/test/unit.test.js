import assert from 'node:assert/strict';
import { test } from 'node:test';
import { hasPermission } from '../src/middleware/auth.js';
import { normalizeEmail, normalizeIndianMobile } from '../src/utils/contact.js';
import { toCsv } from '../src/utils/csv.js';

test('normalizeIndianMobile handles common formats', () => {
  assert.equal(normalizeIndianMobile('+91 98765 43210'), '+919876543210');
  assert.equal(normalizeIndianMobile('098765-43210'), '+919876543210');
  assert.equal(normalizeIndianMobile('9876543210'), '+919876543210');
  assert.equal(normalizeIndianMobile('0172-2701234'), null); // landline
  assert.equal(normalizeIndianMobile('5876543210'), null);
  assert.equal(normalizeIndianMobile(null), null);
});

test('normalizeEmail lowercases and validates', () => {
  assert.equal(normalizeEmail('  Ar.Singh@Example.COM '), 'ar.singh@example.com');
  assert.equal(normalizeEmail('not-an-email'), null);
});

test('toCsv escapes quotes and neutralises formulas', () => {
  const csv = toCsv([{ a: 'x,"y"', b: '=HYPERLINK("evil")' }], ['a', 'b']);
  assert.equal(csv, 'a,b\r\n"x,""y""","\'=HYPERLINK(""evil"")"\r\n');
});

test('RBAC permission map', () => {
  assert.ok(hasPermission('admin', 'users:manage'));
  assert.ok(hasPermission('manager', 'leads:export'));
  assert.ok(!hasPermission('sales', 'leads:export'));
  assert.ok(!hasPermission('viewer', 'leads:write'));
  assert.ok(!hasPermission('unknown', 'leads:read'));
});
