import test from 'node:test';
import assert from 'node:assert/strict';
import { matchCommand, normalizeArabic } from '../src/commands.js';

test('normalizeArabic يوحّد الهمزات والتاء المربوطة', () => {
  assert.equal(normalizeArabic('إلغاء'), 'الغاء');
  assert.equal(normalizeArabic('مساعدة'), 'مساعده');
});

test('matchCommand يتعرف على الأوامر العربية والإنجليزية', () => {
  assert.equal(matchCommand('مساعدة')?.name, 'help');
  assert.equal(matchCommand('/help')?.name, 'help');
  assert.equal(matchCommand('إلغاء')?.name, 'unsubscribe');
  assert.equal(matchCommand('اشتراك')?.name, 'subscribe');
  assert.equal(matchCommand('جديد')?.name, 'reset');
  assert.equal(matchCommand('موجز')?.name, 'brief');
  assert.equal(matchCommand('حالة')?.name, 'status');
});

test('matchCommand يلتقط الوسيط بعد الأمر', () => {
  const command = matchCommand('اخبار غزة');
  assert.equal(command.name, 'news');
  assert.equal(command.args, 'غزة');
});

test('matchCommand يتجاهل الأسئلة العادية', () => {
  assert.equal(matchCommand('وش آخر أخبار المفاوضات النووية؟'), null);
  assert.equal(matchCommand('حلل لي الوضع في السودان'), null);
  assert.equal(matchCommand(''), null);
});
