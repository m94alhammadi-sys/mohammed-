import Anthropic from '@anthropic-ai/sdk';
import { config } from '../config.js';
import { logger } from '../utils/logger.js';

let client = null;

export function getClient() {
  if (!client) {
    if (!config.ai.apiKey) throw new Error('ANTHROPIC_API_KEY غير مضبوط');
    client = new Anthropic({ apiKey: config.ai.apiKey, maxRetries: 3, timeout: 10 * 60 * 1000 });
  }
  return client;
}

/**
 * Feature flags for request shapes that depend on the model and on the
 * account's API version. Anything the API rejects with a 400 is switched off
 * once and stays off for the life of the process, so one bad request does not
 * turn into a failure on every message.
 */
export const features = {
  refusalFallback: config.ai.enableRefusalFallback,
  modernServerTools: true,
  adaptiveThinking: true,
  effort: true,
  midConversationSystem: true,
};

const DOWNGRADES = [
  {
    key: 'refusalFallback',
    matches: (message) => /fallback|server-side-fallback/i.test(message),
    note: 'تم تعطيل fallbacks (غير مدعوم لهذا الحساب أو النموذج)',
  },
  {
    key: 'modernServerTools',
    matches: (message) => /web_search_|web_fetch_|tool.*type|unsupported tool/i.test(message),
    note: 'تم الرجوع لإصدار أقدم من أدوات البحث على الإنترنت',
  },
  {
    key: 'adaptiveThinking',
    matches: (message) => /thinking/i.test(message),
    note: 'تم تعطيل adaptive thinking (غير مدعوم لهذا النموذج)',
  },
  {
    key: 'effort',
    matches: (message) => /effort|output_config/i.test(message),
    note: 'تم تعطيل output_config.effort (غير مدعوم لهذا النموذج)',
  },
  {
    key: 'midConversationSystem',
    matches: (message) => /role 'system'|role "system"|system.*not supported/i.test(message),
    note: 'تم تعطيل رسائل النظام داخل المحادثة (غير مدعومة لهذا النموذج)',
  },
];

function applyDowngrade(error) {
  const message = String(error?.message ?? '');
  for (const rule of DOWNGRADES) {
    if (features[rule.key] && rule.matches(message)) {
      features[rule.key] = false;
      logger.warn(rule.note, { apiError: message.slice(0, 300) });
      return true;
    }
  }
  return false;
}

/**
 * Sends one request, retrying with a reduced feature set if the API rejects an
 * optional parameter. Streaming is used so long answers never hit the HTTP
 * timeout.
 */
export async function sendMessage(buildParams, { maxDowngrades = 4 } = {}) {
  const anthropic = getClient();
  let attempts = 0;

  for (;;) {
    const params = buildParams(features);
    const usesBeta = Boolean(params.betas?.length);
    const namespace = usesBeta ? anthropic.beta.messages : anthropic.messages;
    try {
      const stream = namespace.stream(params);
      return await stream.finalMessage();
    } catch (error) {
      if (error instanceof Anthropic.BadRequestError && attempts < maxDowngrades && applyDowngrade(error)) {
        attempts += 1;
        continue;
      }
      throw error;
    }
  }
}

export { Anthropic };
