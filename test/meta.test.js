import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { verifySignature, parseWebhook } from '../src/whatsapp/meta.js';

const SECRET = 'app-secret-123';
const sign = (body) => `sha256=${crypto.createHmac('sha256', SECRET).update(body).digest('hex')}`;

test('verifySignature يقبل التوقيع الصحيح', () => {
  const body = Buffer.from(JSON.stringify({ hello: 'world' }));
  assert.equal(verifySignature(body, sign(body), SECRET), true);
});

test('verifySignature يرفض التوقيع المزوّر أو الناقص', () => {
  const body = Buffer.from('{"a":1}');
  assert.equal(verifySignature(body, sign(Buffer.from('{"a":2}')), SECRET), false);
  assert.equal(verifySignature(body, 'sha256=deadbeef', SECRET), false);
  assert.equal(verifySignature(body, '', SECRET), false);
  assert.equal(verifySignature(body, undefined, SECRET), false);
  assert.equal(verifySignature(body, sign(body), ''), false);
});

test('parseWebhook يستخرج الرسالة النصية واسم المرسل', () => {
  const payload = {
    entry: [
      {
        changes: [
          {
            value: {
              contacts: [{ wa_id: '971501234567', profile: { name: 'محمد الحمادي' } }],
              messages: [
                {
                  id: 'wamid.1',
                  from: '971501234567',
                  timestamp: '1789200000',
                  type: 'text',
                  text: { body: 'وش آخر الأخبار؟' },
                },
              ],
            },
          },
        ],
      },
    ],
  };
  const [message] = parseWebhook(payload);
  assert.equal(message.id, 'wamid.1');
  assert.equal(message.from, '971501234567');
  assert.equal(message.name, 'محمد الحمادي');
  assert.equal(message.text, 'وش آخر الأخبار؟');
  assert.equal(message.media, null);
});

test('parseWebhook يستخرج الصورة مع التعليق', () => {
  const [message] = parseWebhook({
    entry: [
      {
        changes: [
          {
            value: {
              messages: [
                {
                  id: 'wamid.2',
                  from: '971500000000',
                  type: 'image',
                  image: { id: 'media-1', mime_type: 'image/png', caption: 'وش رايك بهذا الخبر؟' },
                },
              ],
            },
          },
        ],
      },
    ],
  });
  assert.equal(message.type, 'image');
  assert.equal(message.text, 'وش رايك بهذا الخبر؟');
  assert.deepEqual(message.media, { id: 'media-1', mediaType: 'image/png' });
});

test('parseWebhook يتجاهل تحديثات الحالة ولا ينهار على محتوى فارغ', () => {
  assert.deepEqual(parseWebhook({ entry: [{ changes: [{ value: { statuses: [{ status: 'read' }] } }] }] }), []);
  assert.deepEqual(parseWebhook({}), []);
  assert.deepEqual(parseWebhook(null), []);
});
