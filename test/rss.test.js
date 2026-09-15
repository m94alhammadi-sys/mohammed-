import test from 'node:test';
import assert from 'node:assert/strict';
import { parseFeed } from '../src/news/rss.js';
import { dedupe, sortByDate, formatHeadlines } from '../src/news/headlines.js';

const RSS_2 = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>وكالة أنباء</title>
  <item>
    <title>قمة خليجية تبحث الملف الإقليمي</title>
    <link>https://example.com/1</link>
    <description><![CDATA[<p>اجتمع القادة لبحث <b>الأمن</b> الإقليمي</p>]]></description>
    <pubDate>Mon, 14 Sep 2026 09:00:00 GMT</pubDate>
  </item>
  <item>
    <title>مجلس الأمن يصوّت على مشروع قرار</title>
    <link>https://example.com/2</link>
    <pubDate>Tue, 15 Sep 2026 06:30:00 GMT</pubDate>
  </item>
</channel></rss>`;

const ATOM = `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom News</title>
  <entry>
    <title>Elections enter final week</title>
    <link rel="alternate" href="https://example.org/a"/>
    <summary>Campaigning intensifies</summary>
    <updated>2026-09-15T05:00:00Z</updated>
  </entry>
</feed>`;

const RDF = `<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <item>
    <title>تقرير أممي جديد</title>
    <link>https://example.net/r</link>
    <dc:date>2026-09-15T04:00:00Z</dc:date>
  </item>
</rdf:RDF>`;

test('parseFeed يقرأ RSS 2.0 وينظف الوصف', () => {
  const items = parseFeed(RSS_2, { name: 'وكالة', lang: 'ar' });
  assert.equal(items.length, 2);
  assert.equal(items[0].title, 'قمة خليجية تبحث الملف الإقليمي');
  assert.equal(items[0].summary, 'اجتمع القادة لبحث الأمن الإقليمي');
  assert.equal(items[0].link, 'https://example.com/1');
  assert.equal(items[0].source, 'وكالة');
  assert.ok(items[0].publishedAt.startsWith('2026-09-14'));
});

test('parseFeed يقرأ Atom ويستخرج الرابط من السمة href', () => {
  const items = parseFeed(ATOM, { name: 'Atom', lang: 'en' });
  assert.equal(items.length, 1);
  assert.equal(items[0].link, 'https://example.org/a');
  assert.equal(items[0].summary, 'Campaigning intensifies');
});

test('parseFeed يقرأ RDF ويستخدم dc:date', () => {
  const items = parseFeed(RDF, { name: 'UN' });
  assert.equal(items.length, 1);
  assert.ok(items[0].publishedAt.startsWith('2026-09-15'));
});

test('parseFeed لا ينهار على محتوى غير صالح', () => {
  assert.deepEqual(parseFeed('<html><body>خطأ</body></html>', {}), []);
});

test('sortByDate يرتب من الأحدث للأقدم', () => {
  const sorted = sortByDate(parseFeed(RSS_2, { name: 'x' }));
  assert.equal(sorted[0].title, 'مجلس الأمن يصوّت على مشروع قرار');
});

test('dedupe يحذف الخبر المكرر بين المصادر', () => {
  const items = [
    { title: 'قمة خليجية تبحث الملف الإقليمي اليوم', source: 'أ' },
    { title: 'قمة خليجية تبحث الملف الإقليمي', source: 'ب' },
    { title: 'خبر مختلف تماماً عن الاقتصاد', source: 'ج' },
  ];
  assert.equal(dedupe(items).length, 2);
});

test('formatHeadlines ينتج نصاً مرقّماً مع المصدر', () => {
  const output = formatHeadlines([
    { title: 'عنوان', source: 'مصدر', publishedAt: new Date().toISOString(), link: 'https://x.co/1', summary: 'ملخص' },
  ]);
  assert.match(output, /1\. عنوان/);
  assert.match(output, /مصدر/);
  assert.match(output, /https:\/\/x\.co\/1/);
});

test('formatHeadlines يتعامل مع قائمة فارغة', () => {
  assert.match(formatHeadlines([]), /لا توجد عناوين/);
});
