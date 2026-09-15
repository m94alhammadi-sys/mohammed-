import crypto from 'node:crypto';
import { config } from '../config.js';
import { logger } from '../utils/logger.js';

const authHeader = () =>
  `Basic ${Buffer.from(`${config.twilio.accountSid}:${config.twilio.authToken}`).toString('base64')}`;

/**
 * Twilio signs a request by appending the sorted POST parameters to the full
 * webhook URL and taking an HMAC-SHA1 of the result.
 */
export function buildSignature(url, params, authToken) {
  const data = Object.keys(params ?? {})
    .sort()
    .reduce((acc, key) => acc + key + params[key], String(url));
  return crypto.createHmac('sha1', authToken).update(Buffer.from(data, 'utf8')).digest('base64');
}

export function verifySignature(url, params, signature, authToken = config.twilio.authToken) {
  if (!authToken) return false;
  const expected = Buffer.from(buildSignature(url, params, authToken), 'utf8');
  const received = Buffer.from(String(signature ?? ''), 'utf8');
  if (expected.length !== received.length) return false;
  return crypto.timingSafeEqual(expected, received);
}

const stripPrefix = (value) => String(value ?? '').replace(/^whatsapp:/, '');

export function parseWebhook(form) {
  if (!form?.From || !form?.MessageSid) return [];
  const numMedia = Number.parseInt(form.NumMedia ?? '0', 10) || 0;
  const mediaType = form.MediaContentType0 ?? '';
  const media =
    numMedia > 0 && mediaType.startsWith('image/')
      ? { url: form.MediaUrl0, mediaType }
      : null;

  return [
    {
      id: form.MessageSid,
      from: stripPrefix(form.From),
      name: form.ProfileName ?? '',
      timestamp: Date.now(),
      type: media ? 'image' : 'text',
      text: form.Body ?? '',
      media,
    },
  ];
}

export async function sendText(to, text) {
  const body = new URLSearchParams({
    From: config.twilio.from.startsWith('whatsapp:') ? config.twilio.from : `whatsapp:${config.twilio.from}`,
    To: `whatsapp:${to.startsWith('+') ? to : `+${to}`}`,
    Body: text,
  });

  const response = await fetch(
    `https://api.twilio.com/2010-04-01/Accounts/${config.twilio.accountSid}/Messages.json`,
    {
      method: 'POST',
      headers: { authorization: authHeader(), 'content-type': 'application/x-www-form-urlencoded' },
      body,
      signal: AbortSignal.timeout(20000),
    },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`Twilio ${response.status}: ${payload?.message ?? response.statusText}`);
  return payload;
}

export async function downloadMedia(media) {
  const response = await fetch(media.url, {
    headers: { authorization: authHeader() },
    redirect: 'follow',
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error(`تعذر تنزيل الوسائط من Twilio: ${response.status}`);
  const buffer = Buffer.from(await response.arrayBuffer());
  return { data: buffer.toString('base64'), mediaType: media.mediaType || 'image/jpeg' };
}

export const twilioProvider = {
  name: 'twilio',
  sendText,
  markRead: async () => {
    logger.debug('Twilio لا يدعم إشعار القراءة عبر هذا المسار');
    return null;
  },
  downloadMedia,
  verifySignature,
  parseWebhook,
};
