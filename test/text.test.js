import test from 'node:test';
import assert from 'node:assert/strict';
import { chunkText, numberChunks, sanitizeInbound, stripHtml, truncate, formatRelativeTime } from '../src/utils/text.js';

test('chunkText يعيد النص كما هو إذا كان قصيراً', () => {
  assert.deepEqual(chunkText('سلام', 100), ['سلام']);
});

test('chunkText يقسّم النص الطويل ويحترم الحد', () => {
  const paragraph = 'فقرة سياسية طويلة. '.repeat(60);
  const chunks = chunkText(paragraph, 200);
  assert.ok(chunks.length > 1);
  for (const chunk of chunks) assert.ok(chunk.length <= 200, `طول الجزء ${chunk.length}`);
});

test('chunkText يفضّل القطع عند نهاية الفقرة', () => {
  const text = `${'أ'.repeat(120)}\n\n${'ب'.repeat(120)}`;
  const chunks = chunkText(text, 150);
  assert.equal(chunks[0], 'أ'.repeat(120));
});

test('chunkText لا يفقد أي محتوى', () => {
  const text = Array.from({ length: 40 }, (_, i) => `سطر رقم ${i} عن السياسة الدولية`).join('\n');
  const rejoined = chunkText(text, 120).join(' ').replace(/\s+/g, '');
  assert.equal(rejoined, text.replace(/\s+/g, ''));
});

test('numberChunks يرقّم الأجزاء المتعددة فقط', () => {
  assert.deepEqual(numberChunks(['واحد']), ['واحد']);
  const numbered = numberChunks(['واحد', 'اثنان']);
  assert.ok(numbered[0].startsWith('(1/2)'));
  assert.ok(numbered[1].startsWith('(2/2)'));
});

test('sanitizeInbound يزيل محارف التحكم المخفية', () => {
  assert.equal(sanitizeInbound('​سؤال‮ '), 'سؤال');
});

test('stripHtml ينظف الوسوم والسكربتات', () => {
  assert.equal(stripHtml('<p>خبر <b>عاجل</b></p><script>bad()</script>'), 'خبر عاجل');
  assert.equal(stripHtml('&quot;تصريح&quot; &amp; تعليق'), '"تصريح" & تعليق');
});

test('truncate يضيف علامة القطع', () => {
  assert.equal(truncate('abcdef', 3), 'abc…');
  assert.equal(truncate('abc', 5), 'abc');
});

test('formatRelativeTime يصف الفارق الزمني بالعربية', () => {
  const now = new Date('2026-09-15T12:00:00Z');
  assert.equal(formatRelativeTime(new Date('2026-09-15T11:30:00Z'), now), 'قبل 30 دقيقة');
  assert.equal(formatRelativeTime(new Date('2026-09-15T09:00:00Z'), now), 'قبل 3 ساعة');
  assert.equal(formatRelativeTime(new Date('2026-09-13T12:00:00Z'), now), 'قبل 2 يوم');
});
