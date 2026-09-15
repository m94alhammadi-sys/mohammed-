import { config, validateConfig } from './config.js';
import { logger } from './utils/logger.js';
import { createServer } from './server.js';
import { startScheduler } from './scheduler.js';
import { flushSessions } from './store/sessions.js';

const problems = validateConfig();
if (problems.length) {
  logger.error('إعدادات ناقصة، راجع ملف .env', { problems });
  process.exit(1);
}

const app = createServer();
const server = app.listen(config.port, () => {
  logger.info('انطلق خادم وكيل واتساب السياسي', {
    port: config.port,
    provider: config.provider,
    model: config.ai.model,
    webhook: `/webhook`,
  });
});

const task = startScheduler();

async function shutdown(signal) {
  logger.info('إيقاف الخدمة', { signal });
  try {
    task?.stop();
    await flushSessions();
  } finally {
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 5000).unref();
  }
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('unhandledRejection', (reason) => {
  logger.error('وعد مرفوض دون معالجة', { error: String(reason) });
});
