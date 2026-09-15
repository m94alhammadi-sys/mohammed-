import { config } from '../config.js';
import { getHeadlines, formatHeadlines } from '../news/headlines.js';
import { logger } from '../utils/logger.js';

/** Anthropic-hosted tools: search the live web and read specific pages. */
export function serverTools(flags) {
  const searchType = flags.modernServerTools ? config.ai.webSearchToolType : 'web_search_20250305';
  const fetchType = flags.modernServerTools ? config.ai.webFetchToolType : 'web_fetch_20250910';

  const tools = [{ type: searchType, name: 'web_search', max_uses: config.ai.maxWebSearches }];
  if (config.ai.enableWebFetch) {
    tools.push({
      type: fetchType,
      name: 'web_fetch',
      max_uses: config.ai.maxWebFetches,
      citations: { enabled: true },
    });
  }
  return tools;
}

/** Client-side tool: live RSS headlines, general or topic scoped. */
export const HEADLINES_TOOL = {
  name: 'latest_headlines',
  description:
    'يجلب أحدث عناوين الأخبار من تغذيات إخبارية مباشرة (الجزيرة، BBC، العربية، فرانس24، DW، الأمم المتحدة، الغارديان وغيرها). ' +
    'استخدمها للحصول على صورة سريعة عن أبرز ما يجري الآن، أو مرّر موضوعاً محدداً لتصفية العناوين حوله. ' +
    'للتفاصيل الدقيقة والتحقق استخدم web_search بعدها.',
  input_schema: {
    type: 'object',
    properties: {
      topic: {
        type: 'string',
        description: 'موضوع اختياري للبحث عنه في العناوين، مثل "غزة" أو "الانتخابات الأمريكية". اتركه فارغاً لأبرز العناوين عموماً.',
      },
      language: {
        type: 'string',
        enum: ['ar', 'en', 'all'],
        description: 'لغة المصادر. الافتراضي ar.',
      },
      limit: {
        type: 'integer',
        description: 'عدد العناوين المطلوبة (1 إلى 40). الافتراضي 20.',
      },
      hours: {
        type: 'integer',
        description: 'حداثة الأخبار بالساعات (1 إلى 168). الافتراضي 48.',
      },
    },
    required: [],
  },
};

const clamp = (value, min, max, fallback) => {
  const n = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
};

/** Validates the model's arguments before touching the network. */
export async function runHeadlinesTool(rawInput) {
  const input = rawInput && typeof rawInput === 'object' ? rawInput : {};
  const topic = typeof input.topic === 'string' ? input.topic.slice(0, 120).trim() : '';
  const language = ['ar', 'en', 'all'].includes(input.language) ? input.language : 'ar';
  const limit = clamp(input.limit, 1, 40, 20);
  const hours = clamp(input.hours, 1, 168, 48);

  const items = await getHeadlines({ topic, lang: language, limit, freshHours: hours });
  logger.debug('تم تنفيذ أداة العناوين', { topic, language, count: items.length });

  if (!items.length) {
    return 'لم تُرجع التغذيات الإخبارية أي عناوين الآن. استخدم web_search بدلاً من ذلك.';
  }
  const header = topic ? `أحدث العناوين حول "${topic}":` : 'أحدث العناوين السياسية:';
  return `${header}\n${formatHeadlines(items)}`;
}

export const CLIENT_TOOLS = {
  [HEADLINES_TOOL.name]: runHeadlinesTool,
};
