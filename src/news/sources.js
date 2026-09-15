import { config } from '../config.js';

/**
 * Feed list used for the "latest headlines" tool and the daily briefing.
 * lang: ar/en, region: gulf/arab/world. Add more with EXTRA_FEEDS
 * (comma separated "Name|url|lang" entries).
 */
export const FEEDS = [
  { name: 'الجزيرة', url: 'https://www.aljazeera.net/xml/rss/all.xml', lang: 'ar', region: 'arab' },
  { name: 'BBC عربي', url: 'https://feeds.bbci.co.uk/arabic/rss.xml', lang: 'ar', region: 'arab' },
  { name: 'العربية', url: 'https://www.alarabiya.net/.mrss/ar.xml', lang: 'ar', region: 'gulf' },
  { name: 'فرانس 24', url: 'https://www.france24.com/ar/rss', lang: 'ar', region: 'world' },
  { name: 'DW عربية', url: 'https://rss.dw.com/rdf/rss-ar-all', lang: 'ar', region: 'world' },
  { name: 'أخبار الأمم المتحدة', url: 'https://news.un.org/feed/subscribe/ar/news/all/rss.xml', lang: 'ar', region: 'world' },
  { name: 'Al Jazeera English', url: 'https://www.aljazeera.com/xml/rss/all.xml', lang: 'en', region: 'world' },
  { name: 'BBC World', url: 'https://feeds.bbci.co.uk/news/world/rss.xml', lang: 'en', region: 'world' },
  { name: 'The Guardian World', url: 'https://www.theguardian.com/world/rss', lang: 'en', region: 'world' },
  { name: 'NPR World', url: 'https://feeds.npr.org/1004/rss.xml', lang: 'en', region: 'world' },
];

export function allFeeds() {
  const extra = config.news.extraFeeds
    .map((entry) => {
      const [name, url, lang = 'ar', region = 'world'] = entry.split('|').map((part) => part.trim());
      return name && url ? { name, url, lang, region } : null;
    })
    .filter(Boolean);
  return [...FEEDS, ...extra];
}

/**
 * Google News exposes any query as an RSS feed, which gives the agent a
 * topic-scoped headline source without needing a paid news API.
 */
export function topicFeed(topic, { lang = 'ar', country = 'AE' } = {}) {
  const query = encodeURIComponent(String(topic).trim());
  const locale = lang === 'ar' ? `hl=ar&gl=${country}&ceid=${country}:ar` : 'hl=en-US&gl=US&ceid=US:en';
  return {
    name: `بحث الأخبار: ${topic}`,
    url: `https://news.google.com/rss/search?q=${query}&${locale}`,
    lang,
    region: 'search',
  };
}
