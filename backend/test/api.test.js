// Integration tests. Require a disposable Postgres database:
//   TEST_DATABASE_URL=postgres://user:pass@localhost:5432/buildconnect_test npm test
import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';

const dbUrl = process.env.TEST_DATABASE_URL;

describe('API', { skip: !dbUrl && 'TEST_DATABASE_URL not set' }, () => {
  let request, app, pool;
  const tokens = {};
  const INGEST_KEY = 'test-ingest-key';

  before(async () => {
    process.env.NODE_ENV = 'test';
    process.env.DATABASE_URL = dbUrl;
    process.env.INGEST_API_KEY = INGEST_KEY;
    ({ default: request } = await import('supertest'));
    ({ pool } = await import('../src/db/pool.js'));
    await pool.query('DROP SCHEMA public CASCADE; CREATE SCHEMA public;');
    await (await import('../src/db/migrate.js')).migrate();
    app = (await import('../src/app.js')).createApp();

    const bcrypt = (await import('bcryptjs')).default;
    const hash = await bcrypt.hash('password-123', 4);
    for (const role of ['admin', 'manager', 'sales', 'viewer']) {
      await pool.query(
        'INSERT INTO users (email, full_name, password_hash, role) VALUES ($1, $2, $3, $4)',
        [`${role}@test.local`, role, hash, role],
      );
      const res = await request(app).post('/api/auth/login').send({ email: `${role}@test.local`, password: 'password-123' });
      assert.equal(res.status, 200);
      tokens[role] = res.body.token;
    }
  });

  after(() => pool?.end());

  const auth = (role) => ({ Authorization: `Bearer ${tokens[role]}` });
  const sample = (over = {}) => ({
    full_name: 'Ar. Harpreet Kaur',
    firm_name: 'Kaur Design Studio',
    profession: 'architect',
    phone: '+91 98140 12345',
    email: 'harpreet@example.com',
    city: 'Ludhiana',
    state: 'punjab',
    source_url: 'https://directory.example.com/architects/ludhiana',
    confidence: 0.8,
    ...over,
  });

  test('rejects bad credentials and missing tokens', async () => {
    assert.equal((await request(app).post('/api/auth/login').send({ email: 'admin@test.local', password: 'nope' })).status, 401);
    assert.equal((await request(app).get('/api/leads')).status, 401);
  });

  test('ingest requires API key, dedupes and merges', async () => {
    assert.equal((await request(app).post('/api/ingest/leads').send({ leads: [sample()] })).status, 401);

    const run = await request(app).post('/api/ingest/runs').set('x-api-key', INGEST_KEY)
      .send({ agent_name: 'test', target: { state: 'punjab' } });
    assert.equal(run.status, 201);

    const res = await request(app).post('/api/ingest/leads').set('x-api-key', INGEST_KEY).send({
      run_id: run.body.id,
      leads: [
        sample(),
        sample({ email: null, district: 'Ludhiana' }), // same phone -> merge
        sample({ full_name: 'Er. Rakesh Thakur', phone: '9418000001', email: null, state: 'himachal_pradesh',
          profession: 'structural_engineer', city: 'Shimla' }),
        sample({ phone: '12345', email: 'bad' }), // invalid
      ],
    });
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { inserted: 2, merged: 1, suppressed: 0, invalid: 1 });

    const list = await request(app).get('/api/leads?state=punjab').set(auth('viewer'));
    assert.equal(list.body.total, 1);
    assert.equal(list.body.data[0].district, 'Ludhiana');
    assert.equal(list.body.data[0].phone_e164, '+919814012345');
  });

  test('search, stats and export permissions', async () => {
    const search = await request(app).get('/api/leads?q=shimla').set(auth('viewer'));
    assert.equal(search.body.total, 1);

    const stats = await request(app).get('/api/leads/stats').set(auth('viewer'));
    assert.equal(stats.body.total, 2);
    assert.equal(stats.body.by_state.himachal_pradesh, 1);

    assert.equal((await request(app).get('/api/leads/export').set(auth('sales'))).status, 403);
    const csv = await request(app).get('/api/leads/export').set(auth('manager'));
    assert.equal(csv.status, 200);
    assert.match(csv.headers['content-type'], /text\/csv/);
    assert.equal(csv.text.trim().split('\r\n').length, 3);
  });

  test('sales can only edit their own leads and cannot reassign', async () => {
    const { body } = await request(app).get('/api/leads').set(auth('viewer'));
    const id = body.data[0].id;
    const salesId = (await pool.query("SELECT id FROM users WHERE role = 'sales'")).rows[0].id;

    assert.equal((await request(app).patch(`/api/leads/${id}`).set(auth('sales')).send({ status: 'contacted' })).status, 403);
    assert.equal((await request(app).patch(`/api/leads/${id}`).set(auth('viewer')).send({ status: 'contacted' })).status, 403);
    assert.equal((await request(app).patch(`/api/leads/${id}`).set(auth('manager')).send({ assigned_to: salesId })).status, 200);

    const ok = await request(app).patch(`/api/leads/${id}`).set(auth('sales')).send({ status: 'contacted', notes: 'Called' });
    assert.equal(ok.status, 200);
    assert.equal(ok.body.status, 'contacted');
    assert.equal((await request(app).patch(`/api/leads/${id}`).set(auth('sales')).send({ assigned_to: null })).status, 403);
  });

  test('suppression deletes the lead and blocks re-ingest', async () => {
    const res = await request(app).post('/api/suppression').set(auth('manager'))
      .send({ value: '094180 00001', reason: 'Opt-out by phone' });
    assert.equal(res.status, 201);
    assert.equal(res.body.leads_deleted, 1);

    const again = await request(app).post('/api/ingest/leads').set('x-api-key', INGEST_KEY)
      .send({ leads: [sample({ full_name: 'Er. Rakesh Thakur', phone: '9418000001', email: null })] });
    assert.equal(again.body.suppressed, 1);
    assert.equal((await request(app).post('/api/suppression').set(auth('sales')).send({ value: 'a@b.com' })).status, 403);
  });

  test('only admins manage users', async () => {
    const body = { email: 'new@test.local', full_name: 'New', password: 'long-password-1', role: 'sales' };
    assert.equal((await request(app).post('/api/users').set(auth('manager')).send(body)).status, 403);
    assert.equal((await request(app).post('/api/users').set(auth('admin')).send(body)).status, 201);
    assert.equal((await request(app).post('/api/users').set(auth('admin')).send(body)).status, 409);
  });
});
