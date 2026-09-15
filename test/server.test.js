import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-server-'));
process.env.DATA_DIR = tmp;
process.env.WHATSAPP_PROVIDER = 'meta';
process.env.META_VERIFY_TOKEN = 'verify-me';
process.env.META_APP_SECRET = 'top-secret';
process.env.ANTHROPIC_API_KEY = 'test-key';

const { createServer } = await import('../src/server.js');

const server = createServer().listen(0);
await new Promise((resolve) => server.once('listening', resolve));
const base = `http://127.0.0.1:${server.address().port}`;

test.after(() => {
  server.close();
  fs.rmSync(tmp, { recursive: true, force: true });
});

const sign = (body) => `sha256=${crypto.createHmac('sha256', 'top-secret').update(body).digest('hex')}`;

test('GET /health يعيد حالة الخدمة', async () => {
  const response = await fetch(`${base}/health`);
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.status, 'ok');
  assert.equal(payload.provider, 'meta');
});

test('GET /webhook ينجح بالتحقق الصحيح ويعيد التحدي', async () => {
  const response = await fetch(
    `${base}/webhook?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=12345`,
  );
  assert.equal(response.status, 200);
  assert.equal(await response.text(), '12345');
});

test('GET /webhook يرفض رمز تحقق خاطئ', async () => {
  const response = await fetch(
    `${base}/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=12345`,
  );
  assert.equal(response.status, 403);
});

test('POST /webhook يرفض التوقيع غير الصالح', async () => {
  const body = JSON.stringify({ entry: [] });
  const response = await fetch(`${base}/webhook`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-hub-signature-256': 'sha256=bad' },
    body,
  });
  assert.equal(response.status, 403);
});

test('POST /webhook يقبل التوقيع الصحيح ويرد فوراً', async () => {
  // A status-only payload carries no user message, so nothing is dispatched.
  const body = JSON.stringify({
    entry: [{ changes: [{ value: { statuses: [{ id: 'wamid.x', status: 'delivered' }] } }] }],
  });
  const response = await fetch(`${base}/webhook`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-hub-signature-256': sign(Buffer.from(body)) },
    body,
  });
  assert.equal(response.status, 200);
});
