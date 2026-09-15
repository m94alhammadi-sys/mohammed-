import { config } from '../config.js';
import { allFeeds, topicFeed } from './sources.js';
import { fetchFeed } from './rss.js';
import { formatRelativeTime, truncate } from '../utils/text.js';

const cache = new Map();

const cacheKey = (parts) => JSON.stringify(parts);

function normalizeTitle(title) {
  return String(title)
    .replace(/[\u064B-\u0652\u0640]/g, '')
    .replace(/[أإآٱ]/g, 'ا')
    .replace(/[ىئ]/g, 'ي')
    .replace(/ة/g, 'ه')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const STOP_WORDS = new Set(['في', 'من', 'على', 'عن', 'الى', 'ان', 'مع', 'the', 'a', 'of', 'to', 'in', 'and', 'for']);

function titleTokens(title) {
  return new Set(
    normalizeTitle(title)
      .split(' ')
      .filter((word) => word.length > 1 && !STOP_WORDS.has(word)),
  );
}

function similarity(a, b) {
  if (!a.size || !b.size) return 0;
  let shared = 0;
  for (const token of a) if (b.has(token)) shared += 1;
  // Overlap coefficient: a headline that is a longer variant of another still matches.
  return shared / Math.min(a.size, b.size);
}

/** Drops repeats of the same story picked up from several outlets. */
export function dedupe(items, { threshold = 0.8 } = {}) {
  const seen = [];
  const out = [];
  for (const item of items) {
    const tokens = titleTokens(item.title);
    if (!tokens.size) continue;
    if (seen.some((previous) => similarity(tokens, previous) >= threshold)) continue;
    seen.push(tokens);
    out.push(item);
  }
  return out;
}

export function sortByDate(items) {
  return [...items].sort((a, b) => {
    const at = a.publishedAt ? Date.parse(a.publishedAt) : 0;
    const bt = b.publishedAt ? Date.parse(b.publishedAt) : 0;
    return bt - at;
  });
}

/**
 * Pulls headlines from every configured feed (or a topic search feed) in
 * parallel. A slow or broken feed is skipped instead of failing the request.
 */
export async function getHeadlines({ topic = '', lang = 'ar', limit = 25, freshHours = 48 } = {}) {
  const key = cacheKey([topic, lang, limit, freshHours]);
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < config.news.cacheTtlMs) return hit.items;

  const sources = topic
    ? [topicFeed(topic, { lang }), ...allFeeds().filter((feed) => feed.lang === lang)]
    : allFeeds().filter((feed) => (lang === 'all' ? true : feed.lang === lang));

  const results = await Promise.allSettled(sources.map((source) => fetchFeed(source)));
  const items = results.flatMap((result) => (result.status === 'fulfilled' ? result.value : []));

  const cutoff = Date.now() - freshHours * 60 * 60 * 1000;
  const fresh = items.filter((item) => !item.publishedAt || Date.parse(item.publishedAt) >= cutoff);
  const final = dedupe(sortByDate(fresh.length ? fresh : items)).slice(0, limit);

  cache.set(key, { at: Date.now(), items: final });
  return final;
}

export function formatHeadlines(items, { withLinks = true } = {}) {
  if (!items.length) return 'لا توجد عناوين متاحة حالياً من مصادر التغذية.';
  const now = new Date();
  return items
    .map((item, index) => {
      const when = item.publishedAt ? formatRelativeTime(new Date(item.publishedAt), now) : '';
      const meta = [item.source, when].filter(Boolean).join(' · ');
      const link = withLinks && item.link ? `\n   ${item.link}` : '';
      const summary = item.summary ? `\n   ${truncate(item.summary, 200)}` : '';
      return `${index + 1}. ${item.title}\n   [${meta}]${summary}${link}`;
    })
    .join('\n');
}

export function clearHeadlineCache() {
  cache.clear();
}
