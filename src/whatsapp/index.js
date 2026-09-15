import { config } from '../config.js';
import { metaProvider } from './meta.js';
import { twilioProvider } from './twilio.js';
import { chunkText, numberChunks } from '../utils/text.js';
import { logger, redact } from '../utils/logger.js';

export function getProvider(name = config.provider) {
  if (name === 'twilio') return twilioProvider;
  return metaProvider;
}

/** Splits a long answer and sends the parts in order, pacing the API calls. */
export async function sendLongText(to, text, { provider = getProvider(), size = config.limits.chunkSize } = {}) {
  const chunks = numberChunks(chunkText(text, size));
  const sent = [];
  for (const chunk of chunks) {
    try {
      sent.push(await provider.sendText(to, chunk));
    } catch (error) {
      logger.error('فشل إرسال رسالة واتساب', { to: redact(to), error: error.message });
      throw error;
    }
    if (chunks.length > 1) await new Promise((resolve) => setTimeout(resolve, 600));
  }
  return sent;
}

export { metaProvider, twilioProvider };
