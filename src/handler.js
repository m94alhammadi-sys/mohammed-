import { config, isAllowed, normalizePhone } from './config.js';
import { logger, redact } from './utils/logger.js';
import { sanitizeInbound, truncate } from './utils/text.js';
import {
  isDuplicate,
  touchUser,
  getHistory,
  appendHistory,
  checkRateLimit,
} from './store/sessions.js';
import { matchCommand, runCommand } from './commands.js';
import { ask } from './ai/agent.js';
import { getProvider, sendLongText } from './whatsapp/index.js';

/** One in-flight task per user, so two quick messages never interleave. */
const queues = new Map();

export function enqueue(phone, task) {
  const key = normalizePhone(phone);
  const previous = queues.get(key) ?? Promise.resolve();
  const next = previous.then(task, task).catch((error) => {
    logger.error('فشل تنفيذ مهمة في الطابور', { phone: redact(key), error: error.message });
  });
  queues.set(key, next);
  next.finally(() => {
    if (queues.get(key) === next) queues.delete(key);
  });
  return next;
}

const UNSUPPORTED_TYPES = {
  audio: 'ما أقدر أسمع الرسائل الصوتية حالياً. اكتب سؤالك نصاً وأرد عليك.',
  video: 'ما أقدر أشوف الفيديو حالياً. أرسل صورة أو نص أو رابط.',
  document: 'ما أقدر أقرأ الملفات حالياً. أرسل الرابط أو انسخ النص المهم.',
  sticker: 'وصلني الملصق 🙂 اكتب سؤالك السياسي وأبحث لك.',
  location: 'وصلني الموقع. اكتب سؤالك وأرد عليك.',
  contacts: 'وصلتني جهة الاتصال. اكتب سؤالك وأرد عليك.',
};

const MAX_IMAGE_BYTES = 4 * 1024 * 1024;

async function loadImages(message, provider) {
  if (!message.media) return [];
  try {
    const media = provider.name === 'twilio' ? await provider.downloadMedia(message.media) : await provider.downloadMedia(message.media.id);
    const bytes = Buffer.byteLength(media.data, 'base64');
    if (bytes > MAX_IMAGE_BYTES) {
      logger.warn('تم تجاوز حجم الصورة المسموح', { bytes });
      return [];
    }
    if (!String(media.mediaType).startsWith('image/')) return [];
    return [media];
  } catch (error) {
    logger.warn('تعذر تحميل الصورة', { error: error.message });
    return [];
  }
}

function appendSources(text, sources = []) {
  if (!sources.length) return text;
  if (/https?:\/\//i.test(text) || /المصادر\s*:/.test(text)) return text;
  const lines = sources.slice(0, 3).map((source) => `• ${truncate(source.title || source.url, 70)}\n  ${source.url}`);
  return `${text}\n\nالمصادر:\n${lines.join('\n')}`;
}

/**
 * Full pipeline for one inbound WhatsApp message: dedupe, access control,
 * rate limit, command routing, then the agent.
 */
export async function handleMessage(message, provider = getProvider(), { agent = ask } = {}) {
  const phone = normalizePhone(message.from);
  if (!phone) return { status: 'ignored' };

  if (isDuplicate(message.id)) {
    logger.debug('رسالة مكررة، تم تجاهلها', { id: message.id });
    return { status: 'duplicate' };
  }

  if (!isAllowed(phone)) {
    logger.warn('رقم غير مصرّح له', { phone: redact(phone) });
    await provider.sendText(phone, 'هذا المساعد خاص وغير متاح لهذا الرقم.').catch(() => {});
    return { status: 'denied' };
  }

  await provider.markRead(message.id).catch(() => {});

  const rate = checkRateLimit(phone);
  if (!rate.allowed) {
    const minutes = Math.ceil(rate.retryAfterMs / 60000);
    await sendLongText(phone, `وصلت الحد المسموح من الرسائل في الساعة. جرّب بعد ${minutes} دقيقة.`, { provider });
    return { status: 'rate_limited' };
  }

  const user = touchUser(phone, message.name);
  const text = truncate(sanitizeInbound(message.text), config.limits.maxInboundChars);
  const images = await loadImages(message, provider);

  if (!text && !images.length) {
    const hint = UNSUPPORTED_TYPES[message.type] ?? 'اكتب سؤالك السياسي وأرد عليك بتحليل ومصادر.';
    await sendLongText(phone, hint, { provider });
    return { status: 'unsupported' };
  }

  // First contact gets a short greeting before the answer.
  if (user.messageCount === 1 && !matchCommand(text)) {
    const firstName = message.name ? message.name.split(' ')[0] : '';
    await sendLongText(
      phone,
      `أهلاً ${firstName} 👋 أنا مستشارك السياسي. أبحث لك في الإنترنت وأرد بتحليل ومصادر. اكتب "مساعدة" للأوامر.`.replace(/\s+/g, ' ').trim(),
      { provider },
    );
  }

  const command = matchCommand(text);
  if (command && !images.length) {
    logger.info('تنفيذ أمر', { command: command.name, phone: redact(phone) });
    try {
      const result = await runCommand(command, { phone });
      await sendLongText(phone, appendSources(result.text, result.sources), { provider });
      return { status: 'command', command: command.name };
    } catch (error) {
      logger.error('فشل تنفيذ الأمر', { command: command.name, error: error.message });
      await sendLongText(phone, 'صار خلل أثناء تنفيذ الأمر. جرّب مرة ثانية بعد شوي.', { provider });
      return { status: 'error' };
    }
  }

  logger.info('سؤال جديد', { phone: redact(phone), chars: text.length, images: images.length });
  const startedAt = Date.now();

  try {
    const result = await agent({ history: getHistory(phone), text, images });
    const reply = appendSources(result.text || 'ما حصلت إجابة واضحة. جرّب تعيد صياغة السؤال.', result.sources);

    if (!result.refused) {
      appendHistory(phone, [
        { role: 'user', content: text },
        { role: 'assistant', content: result.text },
      ]);
    }

    await sendLongText(phone, reply, { provider });
    logger.info('تم الرد', {
      phone: redact(phone),
      ms: Date.now() - startedAt,
      iterations: result.iterations,
      sources: result.sources?.length ?? 0,
      inputTokens: result.usage?.input_tokens,
      outputTokens: result.usage?.output_tokens,
    });
    return { status: 'answered', result };
  } catch (error) {
    logger.error('فشل توليد الرد', { phone: redact(phone), error: error.message });
    const friendly =
      error?.status === 429
        ? 'الخدمة مزدحمة حالياً. أعد المحاولة بعد دقيقة.'
        : 'صار خلل تقني أثناء البحث والتحليل. أعد إرسال السؤال بعد شوي.';
    await sendLongText(phone, friendly, { provider }).catch(() => {});
    return { status: 'error' };
  }
}

export function handleInbound(messages, provider = getProvider(), options = {}) {
  for (const message of messages) {
    enqueue(message.from, () => handleMessage(message, provider, options));
  }
}
