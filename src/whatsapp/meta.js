import crypto from 'node:crypto';
import { config } from '../config.js';
import { logger, redact } from '../utils/logger.js';

const graphUrl = (path) => `https://graph.facebook.com/${config.meta.graphVersion}/${path}`;

/**
 * Meta signs every webhook body with the app secret. Comparing with
 * timingSafeEqual avoids leaking the expected digest through timing.
 */
export function verifySignature(rawBody, signatureHeader, appSecret = config.meta.appSecret) {
  if (!appSecret) return false;
  const header = String(signatureHeader ?? '');
  if (!header.startsWith('sha256=')) return false;
  const expected = crypto.createHmac('sha256', appSecret).update(rawBody).digest('hex');
  const received = header.slice('sha256='.length);
  const expectedBuf = Buffer.from(expected, 'utf8');
  const receivedBuf = Buffer.from(received, 'utf8');
  if (expectedBuf.length !== receivedBuf.length) return false;
  return crypto.timingSafeEqual(expectedBuf, receivedBuf);
}

/** Flattens the Cloud API webhook envelope into a list of inbound messages. */
export function parseWebhook(body) {
  const out = [];
  for (const entry of body?.entry ?? []) {
    for (const change of entry?.changes ?? []) {
      const value = change?.value ?? {};
      const contacts = value.contacts ?? [];
      for (const message of value.messages ?? []) {
        const contact = contacts.find((item) => item?.wa_id === message.from) ?? contacts[0];
        const base = {
          id: message.id,
          from: message.from,
          name: contact?.profile?.name ?? '',
          timestamp: message.timestamp ? Number(message.timestamp) * 1000 : Date.now(),
          type: message.type,
          text: '',
          media: null,
        };

        switch (message.type) {
          case 'text':
            base.text = message.text?.body ?? '';
            break;
          case 'image':
            base.text = message.image?.caption ?? '';
            base.media = { id: message.image?.id, mediaType: message.image?.mime_type ?? 'image/jpeg' };
            break;
          case 'button':
            base.text = message.button?.text ?? '';
            break;
          case 'interactive':
            base.text =
              message.interactive?.button_reply?.title ?? message.interactive?.list_reply?.title ?? '';
            break;
          default:
            base.text = '';
        }
        out.push(base);
      }
    }
  }
  return out;
}

async function graphRequest(path, { method = 'POST', body, headers = {} } = {}) {
  const response = await fetch(graphUrl(path), {
    method,
    headers: {
      authorization: `Bearer ${config.meta.token}`,
      'content-type': 'application/json',
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.error?.message ?? response.statusText;
    throw new Error(`Graph API ${response.status}: ${detail}`);
  }
  return payload;
}

export async function sendText(to, text, { previewUrl = true } = {}) {
  return graphRequest(`${config.meta.phoneNumberId}/messages`, {
    body: {
      messaging_product: 'whatsapp',
      recipient_type: 'individual',
      to,
      type: 'text',
      text: { preview_url: previewUrl, body: text },
    },
  });
}

export async function markRead(messageId) {
  if (!config.meta.markAsRead || !messageId) return null;
  try {
    return await graphRequest(`${config.meta.phoneNumberId}/messages`, {
      body: { messaging_product: 'whatsapp', status: 'read', message_id: messageId },
    });
  } catch (error) {
    logger.debug('تعذر تعليم الرسالة كمقروءة', { error: error.message });
    return null;
  }
}

/** Two-step download: resolve the media id to a URL, then fetch the bytes. */
export async function downloadMedia(mediaId) {
  const meta = await graphRequest(mediaId, { method: 'GET' });
  if (!meta?.url) throw new Error('لم يُرجع Graph API رابط الوسائط');
  const response = await fetch(meta.url, {
    headers: { authorization: `Bearer ${config.meta.token}` },
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error(`تعذر تنزيل الوسائط: ${response.status}`);
  const buffer = Buffer.from(await response.arrayBuffer());
  logger.debug('تم تنزيل وسائط', { id: redact(mediaId), bytes: buffer.length });
  return { data: buffer.toString('base64'), mediaType: meta.mime_type ?? 'image/jpeg' };
}

export const metaProvider = {
  name: 'meta',
  sendText,
  markRead,
  downloadMedia,
  verifySignature,
  parseWebhook,
};
