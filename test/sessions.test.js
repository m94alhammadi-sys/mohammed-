import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// Point the store at a throwaway directory before config is imported.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-sessions-'));
process.env.DATA_DIR = tmp;
process.env.ALLOWED_NUMBERS = '+971 50 123 4567, 971509999999';
process.env.MESSAGES_PER_HOUR = '3';

const { isAllowed, normalizePhone } = await import('../src/config.js');
const sessions = await import('../src/store/sessions.js');

test.after(() => fs.rmSync(tmp, { recursive: true, force: true }));

test('normalizePhone يحتفظ بالأرقام فقط', () => {
  assert.equal(normalizePhone('+971 50 123 4567'), '971501234567');
  assert.equal(normalizePhone('whatsapp:+971-50-123-4567'), '971501234567');
});

test('isAllowed يحترم القائمة البيضاء بصرف النظر عن التنسيق', () => {
  assert.equal(isAllowed('971501234567'), true);
  assert.equal(isAllowed('+971 509999999'), true);
  assert.equal(isAllowed('971555555555'), false);
});

test('السجل يُقصّ عند الحد الأقصى ويُمسح عند الطلب', () => {
  const phone = '971501234567';
  for (let i = 0; i < 60; i += 1) {
    sessions.appendHistory(phone, [
      { role: 'user', content: `سؤال ${i}` },
      { role: 'assistant', content: `جواب ${i}` },
    ]);
  }
  const history = sessions.getHistory(phone);
  assert.ok(history.length <= 40, `طول السجل ${history.length}`);
  assert.equal(history.at(-1).content, 'جواب 59');

  sessions.clearHistory(phone);
  assert.deepEqual(sessions.getHistory(phone), []);
});

test('checkRateLimit يوقف الرقم بعد تجاوز الحد', () => {
  const phone = '971509999999';
  assert.equal(sessions.checkRateLimit(phone).allowed, true);
  assert.equal(sessions.checkRateLimit(phone).allowed, true);
  assert.equal(sessions.checkRateLimit(phone).allowed, true);
  const blocked = sessions.checkRateLimit(phone);
  assert.equal(blocked.allowed, false);
  assert.ok(blocked.retryAfterMs > 0);
});

test('isDuplicate يمنع معالجة نفس الرسالة مرتين', () => {
  assert.equal(sessions.isDuplicate('wamid.abc'), false);
  assert.equal(sessions.isDuplicate('wamid.abc'), true);
  assert.equal(sessions.isDuplicate('wamid.xyz'), false);
});

test('الاشتراك يُحفظ ويظهر في قائمة المشتركين', () => {
  sessions.setSubscribed('971501234567', true);
  assert.ok(sessions.listSubscribers().includes('971501234567'));
  sessions.setSubscribed('971501234567', false);
  assert.ok(!sessions.listSubscribers().includes('971501234567'));
});

test('البيانات تُكتب على القرص بشكل ذرّي', async () => {
  sessions.setSubscribed('971509999999', true);
  await sessions.flushSessions();
  const file = path.join(tmp, 'sessions.json');
  const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
  assert.equal(saved.users['971509999999'].subscribed, true);
  assert.equal(fs.readdirSync(tmp).filter((name) => name.endsWith('.tmp')).length, 0);
});
