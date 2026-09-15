import { XMLParser } from 'fast-xml-parser';
import { config } from '../config.js';
import { logger } from '../utils/logger.js';
import { stripHtml, truncate } from '../utils/text.js';

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@_',
  trimValues: true,
});

const asArray = (value) => (Array.isArray(value) ? value : value === undefined || value === null ? [] : [value]);

const textOf = (node) => {
  if (node === undefined || node === null) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (typeof node === 'object') return String(node['#text'] ?? node['@_href'] ?? '');
  return '';
};

function parseDate(value) {
  const raw = textOf(value);
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function linkOf(entry) {
  if (entry.link && typeof entry.link === 'object' && !Array.isArray(entry.link)) {
    return entry.link['@_href'] || textOf(entry.link);
  }
  if (Array.isArray(entry.link)) {
    const alternate = entry.link.find((item) => item?.['@_rel'] === 'alternate') ?? entry.link[0];
    return alternate?.['@_href'] || textOf(alternate);
  }
  return textOf(entry.link) || textOf(entry.guid) || textOf(entry.id);
}

/** Normalizes RSS 2.0, Atom and RDF into one item shape. */
export function parseFeed(xml, source = {}) {
  const doc = parser.parse(xml);
  const channel = doc?.rss?.channel ?? doc?.channel;
  const atom = doc?.feed;
  const rdf = doc?.['rdf:RDF'];

  const rawItems = channel
    ? asArray(channel.item)
    : atom
      ? asArray(atom.entry)
      : rdf
        ? asArray(rdf.item)
        : [];

  return rawItems
    .map((entry) => {
      const title = stripHtml(textOf(entry.title));
      if (!title) return null;
      const summary = stripHtml(
        textOf(entry.description) || textOf(entry.summary) || textOf(entry['content:encoded']) || textOf(entry.content),
      );
      const published =
        parseDate(entry.pubDate) ||
        parseDate(entry.published) ||
        parseDate(entry.updated) ||
        parseDate(entry['dc:date']);
      return {
        title,
        link: linkOf(entry),
        summary: truncate(summary, 320),
        publishedAt: published ? published.toISOString() : null,
        source: source.name || stripHtml(textOf(channel?.title ?? atom?.title)) || 'مصدر غير معروف',
        lang: source.lang || 'ar',
      };
    })
    .filter(Boolean);
}

export async function fetchFeed(source, { timeoutMs = config.news.feedTimeoutMs, limit = config.news.maxItemsPerFeed } = {}) {
  try {
    const response = await fetch(source.url, {
      signal: AbortSignal.timeout(timeoutMs),
      headers: {
        'user-agent': 'PoliticalWhatsAppAgent/1.0 (+news reader)',
        accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
      },
      redirect: 'follow',
    });
    if (!response.ok) {
      logger.warn('تعذر جلب التغذية الإخبارية', { source: source.name, status: response.status });
      return [];
    }
    const xml = await response.text();
    return parseFeed(xml, source).slice(0, limit);
  } catch (error) {
    logger.warn('خطأ في جلب التغذية الإخبارية', { source: source.name, error: error.message });
    return [];
  }
}
