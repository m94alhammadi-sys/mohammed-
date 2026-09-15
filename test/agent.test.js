import test from 'node:test';
import assert from 'node:assert/strict';

const { runAgent, ask, currentContextLine } = await import('../src/ai/agent.js');

const textBlock = (text) => ({ type: 'text', text });

/** Fake API: returns the queued responses in order and records the params. */
function fakeApi(responses) {
  const calls = [];
  const send = async (buildParams) => {
    const params = buildParams({
      refusalFallback: true,
      modernServerTools: true,
      adaptiveThinking: true,
      effort: true,
      midConversationSystem: true,
    });
    // Snapshot: runAgent mutates the same messages array across iterations.
    calls.push(structuredClone(params));
    const next = responses.shift();
    if (!next) throw new Error('لا توجد استجابة مهيأة');
    return next;
  };
  return { send, calls };
}

test('runAgent يعيد النص ويجمع المصادر من نتائج البحث', async () => {
  const { send, calls } = fakeApi([
    {
      stop_reason: 'end_turn',
      model: 'claude-opus-5',
      usage: { input_tokens: 10, output_tokens: 5 },
      content: [
        {
          type: 'web_search_tool_result',
          content: [{ type: 'web_search_result', url: 'https://reuters.com/x', title: 'تقرير' }],
        },
        textBlock('الخلاصة: الوضع متوتر.'),
      ],
    },
  ]);

  const result = await runAgent({ messages: [{ role: 'user', content: [textBlock('وش صار؟')] }], send });
  assert.equal(result.text, 'الخلاصة: الوضع متوتر.');
  assert.deepEqual(result.sources, [{ url: 'https://reuters.com/x', title: 'تقرير' }]);
  assert.equal(result.iterations, 1);

  const params = calls[0];
  assert.equal(params.model, 'claude-opus-5');
  assert.deepEqual(params.thinking, { type: 'adaptive' });
  assert.equal(params.output_config.effort, 'high');
  assert.equal(params.fallbacks, 'default');
  assert.deepEqual(params.betas, ['server-side-fallback-2026-07-01']);
  assert.equal(params.system[0].cache_control.type, 'ephemeral');
  const toolNames = params.tools.map((tool) => tool.name);
  assert.deepEqual(toolNames, ['web_search', 'web_fetch', 'latest_headlines']);
  assert.equal(params.tools[0].type, 'web_search_20260209');
});

test('runAgent ينفذ أداة العناوين ويعيد نتيجتها للنموذج', async () => {
  const { send, calls } = fakeApi([
    {
      stop_reason: 'tool_use',
      content: [{ type: 'tool_use', id: 'tu_1', name: 'latest_headlines', input: { topic: 'الخليج', limit: 3 } }],
    },
    { stop_reason: 'end_turn', content: [textBlock('ثلاثة عناوين رئيسية اليوم.')] },
  ]);

  const result = await runAgent({ messages: [{ role: 'user', content: [textBlock('عناوين')] }], send });
  assert.equal(result.text, 'ثلاثة عناوين رئيسية اليوم.');
  assert.equal(result.iterations, 2);

  const secondCall = calls[1].messages;
  const toolResultMessage = secondCall.at(-1);
  assert.equal(toolResultMessage.role, 'user');
  assert.equal(toolResultMessage.content[0].type, 'tool_result');
  assert.equal(toolResultMessage.content[0].tool_use_id, 'tu_1');
  assert.equal(secondCall.at(-2).role, 'assistant');
});

test('runAgent يستأنف عند pause_turn', async () => {
  const { send, calls } = fakeApi([
    { stop_reason: 'pause_turn', content: [{ type: 'server_tool_use', id: 's1', name: 'web_search', input: {} }] },
    { stop_reason: 'end_turn', content: [textBlock('اكتمل البحث.')] },
  ]);

  const result = await runAgent({ messages: [{ role: 'user', content: [textBlock('ابحث')] }], send });
  assert.equal(result.text, 'اكتمل البحث.');
  assert.equal(calls[1].messages.at(-1).role, 'assistant');
});

test('runAgent يتعامل مع الرفض برسالة مهذبة دون إسقاط الخدمة', async () => {
  const { send } = fakeApi([
    { stop_reason: 'refusal', stop_details: { type: 'refusal', category: 'cyber' }, content: [] },
  ]);
  const result = await runAgent({ messages: [{ role: 'user', content: [textBlock('...')] }], send });
  assert.equal(result.refused, true);
  assert.match(result.text, /ما أقدر أساعد/);
});

test('runAgent يتوقف عند الحد الأقصى للدورات ويعيد آخر نص متاح', async () => {
  const responses = Array.from({ length: 30 }, () => ({
    stop_reason: 'pause_turn',
    content: [textBlock('جارٍ البحث')],
  }));
  const { send } = fakeApi(responses);
  const result = await runAgent({ messages: [{ role: 'user', content: [textBlock('ابحث')] }], send });
  assert.equal(result.exhausted, true);
  assert.ok(result.iterations <= 12);
});

test('ask يضيف سياق التاريخ كرسالة نظام داخل المحادثة', async () => {
  const { send, calls } = fakeApi([{ stop_reason: 'end_turn', content: [textBlock('جواب')] }]);
  const result = await ask({
    history: [
      { role: 'user', content: 'سؤال قديم' },
      { role: 'assistant', content: 'جواب قديم' },
    ],
    text: 'سؤال جديد',
    send,
  });

  const messages = calls[0].messages;
  assert.equal(messages.length, 4);
  assert.equal(messages.at(-1).role, 'system');
  assert.match(messages.at(-1).content, /التاريخ الآن/);
  assert.equal(messages.at(-2).content.at(-1).text, 'سؤال جديد');
  assert.deepEqual(result.assistantMessage, { role: 'assistant', content: 'جواب' });
});

test('ask يرسل الصور كمحتوى base64 قبل النص', async () => {
  const { send, calls } = fakeApi([{ stop_reason: 'end_turn', content: [textBlock('تحليل الصورة')] }]);
  await ask({ text: 'وش رايك؟', images: [{ mediaType: 'image/png', data: 'AAAA' }], send });
  const content = calls[0].messages[0].content;
  assert.equal(content[0].type, 'image');
  assert.equal(content[0].source.media_type, 'image/png');
  assert.equal(content[1].type, 'text');
});

test('currentContextLine يذكر التاريخ والمنطقة الزمنية', () => {
  const line = currentContextLine(new Date('2026-09-15T08:00:00Z'));
  assert.match(line, /Asia\/Dubai/);
  assert.match(line, /سياق آلي/);
});
