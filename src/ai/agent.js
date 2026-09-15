import { config } from '../config.js';
import { logger } from '../utils/logger.js';
import { sendMessage, features } from './client.js';
import { SYSTEM_PROMPT, BRIEFING_PROMPT } from './systemPrompt.js';
import { serverTools, HEADLINES_TOOL, CLIENT_TOOLS } from './tools.js';

/** Models that accept `{role:"system"}` entries inside `messages`. */
const MID_CONVERSATION_SYSTEM_MODELS = [
  'claude-opus-5',
  'claude-opus-4-8',
  'claude-fable-5',
  'claude-fable-5-1',
  'claude-mythos-5',
  'claude-mythos-5-1',
];

const supportsMidConversationSystem = (model) =>
  MID_CONVERSATION_SYSTEM_MODELS.some((id) => model.startsWith(id));

export function currentContextLine(now = new Date()) {
  const date = new Intl.DateTimeFormat('ar-AE', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: config.briefing.timezone,
  }).format(now);
  const time = new Intl.DateTimeFormat('ar-AE', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: config.briefing.timezone,
  }).format(now);
  return `سياق آلي (لا تذكره في ردك): التاريخ الآن ${date}، الساعة ${time} بتوقيت ${config.briefing.timezone}. أي معلومة بعد تاريخ تدريبك يجب التحقق منها بالبحث.`;
}

function buildParams(flags, { messages, system, maxTokens }) {
  const params = {
    model: config.ai.model,
    max_tokens: maxTokens ?? config.ai.maxTokens,
    system: [{ type: 'text', text: system, cache_control: { type: 'ephemeral' } }],
    tools: [...serverTools(flags), HEADLINES_TOOL],
    messages,
  };

  if (flags.adaptiveThinking) params.thinking = { type: 'adaptive' };
  if (flags.effort) params.output_config = { effort: config.ai.effort };
  if (flags.refusalFallback) {
    // Server-side fallback: if a safety classifier declines, the same request
    // is re-run on a fallback model inside the same API call.
    params.betas = ['server-side-fallback-2026-07-01'];
    params.fallbacks = 'default';
  }
  return params;
}

function textOfMessage(message) {
  return (message.content ?? [])
    .filter((block) => block.type === 'text')
    .map((block) => block.text)
    .join('\n')
    .trim();
}

function collectSources(message, sink) {
  for (const block of message.content ?? []) {
    if (block.type === 'web_search_tool_result' && Array.isArray(block.content)) {
      for (const result of block.content) {
        if (result?.url) sink.set(result.url, result.title || result.url);
      }
    }
    if (block.type === 'web_fetch_tool_result' && block.content && !Array.isArray(block.content)) {
      const url = block.content.url || block.content?.document?.source?.url;
      if (url) sink.set(url, block.content?.document?.title || url);
    }
    if (block.type === 'text' && Array.isArray(block.citations)) {
      for (const citation of block.citations) {
        if (citation?.url) sink.set(citation.url, citation.title || citation.url);
      }
    }
  }
}

async function runClientTools(message) {
  const calls = (message.content ?? []).filter(
    (block) => block.type === 'tool_use' && CLIENT_TOOLS[block.name],
  );
  // Parallel tool calls must come back as tool_result blocks in ONE user message.
  const results = await Promise.all(
    calls.map(async (call) => {
      try {
        const output = await CLIENT_TOOLS[call.name](call.input);
        return { type: 'tool_result', tool_use_id: call.id, content: String(output) };
      } catch (error) {
        logger.warn('فشل تنفيذ أداة', { tool: call.name, error: error.message });
        return {
          type: 'tool_result',
          tool_use_id: call.id,
          is_error: true,
          content: `تعذر تنفيذ الأداة: ${error.message}`,
        };
      }
    }),
  );
  return results;
}

/**
 * Runs the agent loop: the model searches the web, reads pages and pulls RSS
 * headlines until it has an answer. Server tools run on Anthropic's side, the
 * headlines tool runs here.
 */
export async function runAgent({ messages, system = SYSTEM_PROMPT, maxTokens, label = 'chat', send = sendMessage } = {}) {
  const working = [...messages];
  const sources = new Map();
  let iterations = 0;
  let stopReason = null;

  while (iterations < config.ai.maxAgentIterations) {
    iterations += 1;
    const response = await send((flags) => buildParams(flags, { messages: working, system, maxTokens }));
    stopReason = response.stop_reason;
    collectSources(response, sources);

    if (stopReason === 'refusal') {
      logger.warn('رفض النموذج الطلب', { label, category: response.stop_details?.category ?? null });
      return {
        text: 'ما أقدر أساعد في هذا الطلب تحديداً. تقدر تعيد صياغته أو تسألني عن الجانب التحليلي أو الخبري فيه.',
        sources: [],
        refused: true,
        iterations,
        usage: response.usage,
      };
    }

    // Echo the full assistant turn back, including thinking and server-tool
    // blocks, so the next request continues the same reasoning.
    working.push({ role: 'assistant', content: response.content });

    if (stopReason === 'pause_turn') continue;

    if (stopReason === 'tool_use') {
      const toolResults = await runClientTools(response);
      if (toolResults.length === 0) {
        // Server tool use only - nothing to run here, let the model continue.
        continue;
      }
      working.push({ role: 'user', content: toolResults });
      continue;
    }

    const text = textOfMessage(response);
    return {
      text,
      sources: [...sources.entries()].map(([url, title]) => ({ url, title })),
      truncated: stopReason === 'max_tokens',
      iterations,
      usage: response.usage,
      model: response.model,
      assistantContent: response.content,
    };
  }

  logger.warn('تجاوز الوكيل الحد الأقصى للدورات', { label, iterations });
  const lastText = [...working].reverse().find((entry) => entry.role === 'assistant' && textOfMessage(entry));
  return {
    text: lastText ? textOfMessage(lastText) : 'استغرق البحث وقتاً أطول من المتوقع. جرّب تسأل بصيغة أضيق.',
    sources: [...sources.entries()].map(([url, title]) => ({ url, title })),
    exhausted: true,
    iterations,
  };
}

/** One chat turn: history + the new message, with a fresh date context line. */
export async function ask({ history = [], text, images = [], now = new Date(), send = sendMessage } = {}) {
  const content = [];
  for (const image of images) {
    content.push({ type: 'image', source: { type: 'base64', media_type: image.mediaType, data: image.data } });
  }
  content.push({ type: 'text', text });

  const userMessage = { role: 'user', content };
  const messages = [...history, userMessage];

  const contextLine = currentContextLine(now);
  if (features.midConversationSystem && supportsMidConversationSystem(config.ai.model)) {
    messages.push({ role: 'system', content: contextLine });
  } else {
    userMessage.content = [...content.slice(0, -1), { type: 'text', text: `${contextLine}\n\n${text}` }];
  }

  const result = await runAgent({ messages, label: 'chat', send });
  return {
    ...result,
    userMessage: { role: 'user', content: text },
    assistantMessage: { role: 'assistant', content: result.text },
  };
}

/** The scheduled daily briefing, grounded in live headlines. */
export async function buildBriefing({ headlines = '', now = new Date(), send = sendMessage } = {}) {
  const prompt = [
    currentContextLine(now),
    '',
    'هذه عناوين حية مسحوبة قبل قليل من التغذيات الإخبارية. تحقّق من أهمها بالبحث ثم اكتب الموجز:',
    '',
    headlines || '(لم تتوفر عناوين من التغذيات، اعتمد على البحث في الإنترنت)',
  ].join('\n');

  const result = await runAgent({
    messages: [{ role: 'user', content: [{ type: 'text', text: prompt }] }],
    system: `${SYSTEM_PROMPT}\n\n${BRIEFING_PROMPT}`,
    label: 'briefing',
    send,
  });
  return result;
}
