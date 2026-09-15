import cron from 'node-cron';
import { config } from './config.js';
import { logger, redact } from './utils/logger.js';
import { listSubscribers } from './store/sessions.js';
import { getHeadlines, formatHeadlines } from './news/headlines.js';
import { buildBriefing } from './ai/agent.js';
import { getProvider, sendLongText } from './whatsapp/index.js';

/** Builds the briefing once, then fans it out to every subscriber. */
export async function sendDailyBriefing({ provider = getProvider() } = {}) {
  const subscribers = listSubscribers();
  if (!subscribers.length) {
    logger.info('لا يوجد مشتركون في الموجز اليومي');
    return { sent: 0 };
  }

  const items = await getHeadlines({ limit: 30 });
  const briefing = await buildBriefing({ headlines: formatHeadlines(items, { withLinks: false }) });
  if (!briefing.text) {
    logger.warn('تعذر توليد الموجز اليومي');
    return { sent: 0 };
  }

  let sent = 0;
  for (const phone of subscribers) {
    try {
      await sendLongText(phone, briefing.text, { provider });
      sent += 1;
    } catch (error) {
      logger.error('فشل إرسال الموجز', { phone: redact(phone), error: error.message });
    }
  }
  logger.info('تم إرسال الموجز اليومي', { sent, total: subscribers.length });
  return { sent, total: subscribers.length };
}

export function startScheduler() {
  if (!config.briefing.enabled) {
    logger.info('الموجز اليومي معطّل');
    return null;
  }
  if (!cron.validate(config.briefing.cron)) {
    logger.error('صيغة BRIEFING_CRON غير صالحة', { cron: config.briefing.cron });
    return null;
  }

  const task = cron.schedule(
    config.briefing.cron,
    () => {
      sendDailyBriefing().catch((error) =>
        logger.error('فشل تنفيذ مهمة الموجز', { error: error.message }),
      );
    },
    { timezone: config.briefing.timezone },
  );

  logger.info('تم تفعيل جدولة الموجز اليومي', {
    cron: config.briefing.cron,
    timezone: config.briefing.timezone,
  });
  return task;
}
