import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { buildSignature, verifySignature, parseWebhook } from '../src/whatsapp/twilio.js';

// Independent re-implementation of Twilio's documented algorithm: the full
// webhook URL, then every POST parameter sorted by key, HMAC-SHA1, base64.
function referenceSignature(url, params, token) {
  const data = Object.keys(params)
    .sort()
    .reduce((acc, key) => acc + key + params[key], url);
  return crypto.createHmac('sha1', token).update(Buffer.from(data, 'utf8')).digest('base64');
}

const URL = 'https://mycompany.com/myapp.php?foo=1&bar=2';
const PARAMS = {
  Digits: '1234',
  To: '+18005551212',
  From: '+14158675310',
  Caller: '+14158675310',
  CallSid: 'CA1234567890ABCDE',
};

test('buildSignature يطابق الخوارزمية المرجعية لـ Twilio', () => {
  assert.equal(buildSignature(URL, PARAMS, '12345'), referenceSignature(URL, PARAMS, '12345'));
  assert.equal(buildSignature(URL, PARAMS, '12345'), 'GvWf1cFY/Q7PnoempGyD5oXAezc=');
});

test('buildSignature يرتب المعاملات بغض النظر عن ترتيب الإدخال', () => {
  const reordered = { CallSid: PARAMS.CallSid, To: PARAMS.To, Caller: PARAMS.Caller, From: PARAMS.From, Digits: PARAMS.Digits };
  assert.equal(buildSignature(URL, reordered, '12345'), buildSignature(URL, PARAMS, '12345'));
});

test('verifySignature يقبل الصحيح ويرفض الخاطئ', () => {
  const signature = buildSignature(URL, PARAMS, '12345');
  assert.equal(verifySignature(URL, PARAMS, signature, '12345'), true);
  assert.equal(verifySignature(URL, PARAMS, signature, 'wrong-token'), false);
  assert.equal(verifySignature(URL, { ...PARAMS, Digits: '9999' }, signature, '12345'), false);
  assert.equal(verifySignature(URL, PARAMS, 'abc', '12345'), false);
});

test('parseWebhook يحوّل نموذج Twilio إلى رسالة موحّدة', () => {
  const [message] = parseWebhook({
    MessageSid: 'SM123',
    From: 'whatsapp:+971501234567',
    ProfileName: 'محمد',
    Body: 'حلل لي الوضع',
    NumMedia: '0',
  });
  assert.equal(message.id, 'SM123');
  assert.equal(message.from, '+971501234567');
  assert.equal(message.text, 'حلل لي الوضع');
  assert.equal(message.type, 'text');
});

test('parseWebhook يلتقط الصور فقط من الوسائط', () => {
  const [image] = parseWebhook({
    MessageSid: 'SM1',
    From: 'whatsapp:+9715',
    NumMedia: '1',
    MediaContentType0: 'image/jpeg',
    MediaUrl0: 'https://api.twilio.com/media/1',
  });
  assert.equal(image.type, 'image');
  assert.equal(image.media.url, 'https://api.twilio.com/media/1');

  const [audio] = parseWebhook({
    MessageSid: 'SM2',
    From: 'whatsapp:+9715',
    NumMedia: '1',
    MediaContentType0: 'audio/ogg',
    MediaUrl0: 'https://api.twilio.com/media/2',
  });
  assert.equal(audio.media, null);
});

test('parseWebhook يتجاهل الطلبات غير الصالحة', () => {
  assert.deepEqual(parseWebhook({}), []);
});
