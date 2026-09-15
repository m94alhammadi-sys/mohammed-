import { config } from './config.js';
import { clearHistory, setSubscribed, getUser } from './store/sessions.js';
import { getHeadlines, formatHeadlines, clearHeadlineCache } from './news/headlines.js';
import { buildBriefing } from './ai/agent.js';

/** Normalizes Arabic spelling variants so "إلغاء" and "الغاء" match the same command. */
export function normalizeArabic(text) {
  return String(text ?? '')
    .replace(/[ً-ْـ]/g, '')
    .replace(/[أإآٱ]/g, 'ا')
    .replace(/ى/g, 'ي')
    .replace(/ؤ/g, 'و')
    .replace(/ئ/g, 'ي')
    .replace(/ة/g, 'ه')
    .toLowerCase()
    .trim();
}

const COMMANDS = [
  { name: 'help', keywords: ['/help', '/start', 'مساعده', 'مساعدة', 'help', 'اوامر', 'الاوامر', 'menu', '؟', '?'] },
  { name: 'reset', keywords: ['/new', '/reset', 'جديد', 'مسح', 'محادثه جديده', 'ابدا من جديد', 'reset', 'clear', 'new'] },
  { name: 'brief', keywords: ['/brief', 'موجز', 'الموجز', 'بريفنق', 'خلاصه', 'brief', 'briefing'] },
  { name: 'subscribe', keywords: ['/subscribe', 'اشتراك', 'اشتركني', 'فعل الموجز', 'subscribe'] },
  { name: 'unsubscribe', keywords: ['/stop', '/unsubscribe', 'الغاء', 'الغاء الاشتراك', 'ايقاف', 'وقف الموجز', 'unsubscribe', 'stop'] },
  { name: 'news', keywords: ['/news', 'اخبار', 'الاخبار', 'عناوين', 'العناوين', 'news', 'headlines'] },
  { name: 'status', keywords: ['/status', 'حاله', 'الحاله', 'status'] },
];

/**
 * Returns the matched command and any trailing argument, e.g. "اخبار غزة"
 * -> { name: "news", args: "غزة" }. Returns null for ordinary questions.
 */
export function matchCommand(text) {
  const raw = String(text ?? '').trim();
  if (!raw) return null;
  const normalized = normalizeArabic(raw);

  for (const command of COMMANDS) {
    for (const keyword of command.keywords) {
      const key = normalizeArabic(keyword);
      if (normalized === key) return { name: command.name, args: '' };
      if (normalized.startsWith(`${key} `)) {
        return { name: command.name, args: raw.slice(keyword.length).trim() };
      }
    }
  }
  return null;
}

export const HELP_TEXT = `*مستشارك السياسي* 🗞️

اسألني أي سؤال سياسي وأبحث لك في الإنترنت وأرد بتحليل مسنود بمصادر.

*أمثلة:*
• وش آخر تطورات ملف إيران النووي؟
• حلل لي نتائج انتخابات كذا وأثرها على الخليج
• قارن بين موقف الرياض وأبوظبي من هذا الملف
• ارسل لي رابط خبر وأحلله لك

*الأوامر:*
• *اخبار* — أحدث العناوين من المصادر مباشرة (أو "اخبار غزة" لموضوع معيّن)
• *موجز* — موجز سياسي تحليلي الآن
• *اشتراك* — يوصلك الموجز يومياً
• *الغاء* — إيقاف الموجز اليومي
• *جديد* — بدء محادثة جديدة ونسيان السياق السابق
• *حالة* — معلومات الحساب والإعدادات
• *مساعدة* — هذه القائمة`;

export async function runCommand(command, { phone }) {
  switch (command.name) {
    case 'help':
      return { text: HELP_TEXT };

    case 'reset':
      clearHistory(phone);
      return { text: 'تم مسح سياق المحادثة. ابدأ من جديد 👌' };

    case 'subscribe':
      setSubscribed(phone, true);
      return {
        text: `تم تفعيل الموجز اليومي. يوصلك كل يوم الساعة ${config.briefing.cron.split(' ')[1]}:00 بتوقيت ${config.briefing.timezone}.`,
      };

    case 'unsubscribe':
      setSubscribed(phone, false);
      return { text: 'تم إيقاف الموجز اليومي. تقدر ترجعه بكلمة "اشتراك".' };

    case 'news': {
      clearHeadlineCache();
      const items = await getHeadlines({ topic: command.args, limit: command.args ? 12 : 15 });
      const title = command.args ? `*عناوين حول "${command.args}"*` : '*أحدث العناوين*';
      return { text: `${title}\n\n${formatHeadlines(items)}` };
    }

    case 'brief': {
      const items = await getHeadlines({ limit: 30 });
      const result = await buildBriefing({ headlines: formatHeadlines(items, { withLinks: false }) });
      return { text: result.text, sources: result.sources };
    }

    case 'status': {
      const user = getUser(phone);
      return {
        text: [
          '*حالة الحساب*',
          `• النموذج: ${config.ai.model}`,
          `• البحث في الإنترنت: مفعّل`,
          `• الموجز اليومي: ${user.subscribed ? 'مفعّل' : 'متوقف'}`,
          `• عدد رسائلك: ${user.messageCount}`,
          `• طول السياق المحفوظ: ${(user.history ?? []).length} رسالة`,
          `• الحد: ${config.limits.messagesPerHour} رسالة في الساعة`,
        ].join('\n'),
      };
    }

    default:
      return { text: HELP_TEXT };
  }
}
