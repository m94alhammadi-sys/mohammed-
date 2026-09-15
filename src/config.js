import 'dotenv/config';

const bool = (value, fallback = false) => {
  if (value === undefined || value === '') return fallback;
  return ['1', 'true', 'yes', 'y', 'on'].includes(String(value).trim().toLowerCase());
};

const int = (value, fallback) => {
  const n = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(n) ? n : fallback;
};

const list = (value) =>
  String(value ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

/** Digits only, so "+971 50 123 4567" and "97150 1234567" compare equal. */
export const normalizePhone = (value) => String(value ?? '').replace(/\D/g, '');

export const config = {
  env: process.env.NODE_ENV || 'development',
  port: int(process.env.PORT, 3000),
  dataDir: process.env.DATA_DIR || './data',
  logLevel: process.env.LOG_LEVEL || 'info',

  // Which WhatsApp transport to use: "meta" (WhatsApp Cloud API) or "twilio".
  provider: (process.env.WHATSAPP_PROVIDER || 'meta').toLowerCase(),

  meta: {
    token: process.env.META_ACCESS_TOKEN || '',
    phoneNumberId: process.env.META_PHONE_NUMBER_ID || '',
    verifyToken: process.env.META_VERIFY_TOKEN || '',
    appSecret: process.env.META_APP_SECRET || '',
    graphVersion: process.env.META_GRAPH_VERSION || 'v23.0',
    markAsRead: bool(process.env.META_MARK_AS_READ, true),
  },

  twilio: {
    accountSid: process.env.TWILIO_ACCOUNT_SID || '',
    authToken: process.env.TWILIO_AUTH_TOKEN || '',
    from: process.env.TWILIO_WHATSAPP_FROM || '',
    // Public URL of the webhook, needed to validate Twilio's signature.
    webhookUrl: process.env.TWILIO_WEBHOOK_URL || '',
    validateSignature: bool(process.env.TWILIO_VALIDATE_SIGNATURE, true),
  },

  ai: {
    apiKey: process.env.ANTHROPIC_API_KEY || '',
    model: process.env.ANTHROPIC_MODEL || 'claude-opus-5',
    effort: process.env.ANTHROPIC_EFFORT || 'high',
    maxTokens: int(process.env.ANTHROPIC_MAX_TOKENS, 16000),
    // Server tool type strings. Newer models take the _20260209 variants;
    // older ones need web_search_20250305 / web_fetch_20250910.
    webSearchToolType: process.env.WEB_SEARCH_TOOL_TYPE || 'web_search_20260209',
    webFetchToolType: process.env.WEB_FETCH_TOOL_TYPE || 'web_fetch_20260209',
    maxWebSearches: int(process.env.MAX_WEB_SEARCHES, 8),
    maxWebFetches: int(process.env.MAX_WEB_FETCHES, 5),
    enableWebFetch: bool(process.env.ENABLE_WEB_FETCH, true),
    enableRefusalFallback: bool(process.env.ENABLE_REFUSAL_FALLBACK, true),
    maxAgentIterations: int(process.env.MAX_AGENT_ITERATIONS, 12),
    // How many past turns (user + assistant) to replay to the model.
    historyTurns: int(process.env.HISTORY_TURNS, 20),
  },

  limits: {
    // Per-user throttle so a runaway chat cannot burn the API budget.
    messagesPerHour: int(process.env.MESSAGES_PER_HOUR, 30),
    maxInboundChars: int(process.env.MAX_INBOUND_CHARS, 4000),
    // WhatsApp hard limit is 4096 characters per text message.
    chunkSize: int(process.env.OUTBOUND_CHUNK_SIZE, 3500),
  },

  access: {
    // Empty list = open to everyone. Recommended: list your own numbers.
    allowedNumbers: list(process.env.ALLOWED_NUMBERS).map(normalizePhone),
  },

  briefing: {
    enabled: bool(process.env.BRIEFING_ENABLED, true),
    // node-cron expression, evaluated in BRIEFING_TIMEZONE.
    cron: process.env.BRIEFING_CRON || '0 7 * * *',
    timezone: process.env.BRIEFING_TIMEZONE || 'Asia/Dubai',
    // Extra numbers that always receive the briefing.
    defaultSubscribers: list(process.env.BRIEFING_SUBSCRIBERS).map(normalizePhone),
  },

  news: {
    feedTimeoutMs: int(process.env.FEED_TIMEOUT_MS, 8000),
    maxItemsPerFeed: int(process.env.MAX_ITEMS_PER_FEED, 8),
    cacheTtlMs: int(process.env.FEED_CACHE_TTL_MS, 5 * 60 * 1000),
    extraFeeds: list(process.env.EXTRA_FEEDS),
  },
};

export function validateConfig({ requireWhatsApp = true } = {}) {
  const problems = [];
  if (!config.ai.apiKey) problems.push('ANTHROPIC_API_KEY مفقود');

  if (requireWhatsApp && config.provider === 'meta') {
    if (!config.meta.token) problems.push('META_ACCESS_TOKEN مفقود');
    if (!config.meta.phoneNumberId) problems.push('META_PHONE_NUMBER_ID مفقود');
    if (!config.meta.verifyToken) problems.push('META_VERIFY_TOKEN مفقود');
    if (!config.meta.appSecret) problems.push('META_APP_SECRET مفقود (التحقق من توقيع الويبهوك)');
  }

  if (requireWhatsApp && config.provider === 'twilio') {
    if (!config.twilio.accountSid) problems.push('TWILIO_ACCOUNT_SID مفقود');
    if (!config.twilio.authToken) problems.push('TWILIO_AUTH_TOKEN مفقود');
    if (!config.twilio.from) problems.push('TWILIO_WHATSAPP_FROM مفقود');
    if (config.twilio.validateSignature && !config.twilio.webhookUrl) {
      problems.push('TWILIO_WEBHOOK_URL مفقود (مطلوب للتحقق من التوقيع)');
    }
  }

  if (requireWhatsApp && !['meta', 'twilio'].includes(config.provider)) {
    problems.push(`WHATSAPP_PROVIDER غير معروف: ${config.provider}`);
  }

  return problems;
}

export function isAllowed(phone) {
  if (config.access.allowedNumbers.length === 0) return true;
  return config.access.allowedNumbers.includes(normalizePhone(phone));
}
