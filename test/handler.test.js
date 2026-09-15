import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-handler-'));
process.env.DATA_DIR = tmp;
// A dedicated number per test: the rate limiter is per-number and persists
// across tests in this file.
const PHONES = Array.from({ length: 12 }, (_, i) => `9715000000${String(i).padStart(2, '0')}`);
process.env.ALLOWED_NUMBERS = PHONES.join(',');
process.env.MESSAGES_PER_HOUR = '5';
process.env.OUTBOUND_CHUNK_SIZE = '200';

const { handleMessage } = await import('../src/handler.js');

test.after(() => fs.rmSync(tmp, { recursive: true, force: true }));

/** Records everything the bot would send, instead of calling WhatsApp. */
function fakeProvider() {
  const sent = [];
  return {
    name: 'meta',
    sent,
    sendText: async (to, text) => {
      sent.push({ to, text });
      return { id: `m${sent.length}` };
    },
    markRead: async () => null,
    downloadMedia: async () => ({ data: 'AAAA', mediaType: 'image/jpeg' }),
  };
}

const allText = (provider) => provider.sent.map((message) => message.text).join('\n');

const inbound = (overrides = {}) => ({
  id: `wamid.${Math.random()}`,
  from: PHONES[0],
  name: 'محمد',
  type: 'text',
  text: 'سؤال',
  media: null,
  ...overrides,
});

test('الرسالة العادية تمر للوكيل ويُرسل الرد', async () => {
  const provider = fakeProvider();
  const agent = async () => ({ text: 'الجواب التحليلي', sources: [], iterations: 1 });
  const result = await handleMessage(inbound({ from: PHONES[1], text: 'وش آخر الأخبار؟' }), provider, { agent });

  assert.equal(result.status, 'answered');
  assert.ok(provider.sent.some((message) => message.text === 'الجواب التحليلي'));
});

test('المصادر تُضاف عندما لا يذكرها الرد', async () => {
  const provider = fakeProvider();
  const agent = async () => ({
    text: 'تحليل بدون روابط',
    sources: [{ url: 'https://reuters.com/a', title: 'رويترز' }],
  });
  await handleMessage(inbound({ from: PHONES[2] }), provider, { agent });
  assert.match(allText(provider), /المصادر:/);
  assert.match(allText(provider), /https:\/\/reuters\.com\/a/);
});

test('الرد الطويل يُقسّم إلى رسائل مرقّمة', async () => {
  const provider = fakeProvider();
  const agent = async () => ({ text: 'تحليل مطوّل. '.repeat(80), sources: [] });
  await handleMessage(inbound({ from: PHONES[3] }), provider, { agent });
  assert.ok(provider.sent.length > 1);
  // The very first message to a new user is the greeting, the answer follows.
  assert.ok(provider.sent.some((message) => /^\(1\//.test(message.text)));
  assert.ok(provider.sent.some((message) => /^\(2\//.test(message.text)));
});

test('الرسالة المكررة تُتجاهل', async () => {
  const provider = fakeProvider();
  const agent = async () => ({ text: 'جواب', sources: [] });
  const message = inbound({ id: 'wamid.dup', from: PHONES[4] });
  await handleMessage(message, provider, { agent });
  const second = await handleMessage(message, provider, { agent });
  assert.equal(second.status, 'duplicate');
});

test('الرقم غير المصرّح له يُرفض قبل استدعاء الوكيل', async () => {
  const provider = fakeProvider();
  let called = false;
  const agent = async () => {
    called = true;
    return { text: 'x', sources: [] };
  };
  const result = await handleMessage(inbound({ from: '971555555555' }), provider, { agent });
  assert.equal(result.status, 'denied');
  assert.equal(called, false);
});

test('الأوامر تُنفّذ محلياً بدون استدعاء النموذج', async () => {
  const provider = fakeProvider();
  let called = false;
  const agent = async () => {
    called = true;
    return { text: 'x', sources: [] };
  };
  const result = await handleMessage(inbound({ from: PHONES[5], text: 'مساعدة' }), provider, { agent });
  assert.equal(result.status, 'command');
  assert.equal(called, false);
  assert.match(allText(provider), /الأوامر/);
});

test('أمر "جديد" يمسح السياق', async () => {
  const provider = fakeProvider();
  const agent = async () => ({ text: 'جواب', sources: [] });
  await handleMessage(inbound({ from: PHONES[6], text: 'سؤال أول' }), provider, { agent });
  const result = await handleMessage(inbound({ from: PHONES[6], text: 'جديد' }), provider, { agent });
  assert.equal(result.command, 'reset');
  assert.match(allText(provider), /تم مسح/);
});

test('الرسائل الصوتية تحصل على رد إرشادي', async () => {
  const provider = fakeProvider();
  const agent = async () => ({ text: 'x', sources: [] });
  const result = await handleMessage(inbound({ from: PHONES[7], type: 'audio', text: '' }), provider, { agent });
  assert.equal(result.status, 'unsupported');
  assert.match(allText(provider), /الرسائل الصوتية/);
});

test('فشل النموذج يُترجم إلى رسالة واضحة للمستخدم', async () => {
  const provider = fakeProvider();
  const agent = async () => {
    throw new Error('boom');
  };
  const result = await handleMessage(inbound({ from: PHONES[8] }), provider, { agent });
  assert.equal(result.status, 'error');
  assert.match(allText(provider), /خلل تقني/);
});

test('تجاوز الحد يوقف الرد على الرسائل الإضافية', async () => {
  const provider = fakeProvider();
  const agent = async () => ({ text: 'جواب', sources: [] });
  let lastStatus = '';
  for (let i = 0; i < 8; i += 1) {
    lastStatus = (await handleMessage(inbound({ from: PHONES[9], text: `سؤال ${i}` }), provider, { agent })).status;
  }
  assert.equal(lastStatus, 'rate_limited');
  assert.match(allText(provider), /الحد المسموح/);
});
