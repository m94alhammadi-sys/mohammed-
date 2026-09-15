import express from 'express';
import { config } from './config.js';
import { logger } from './utils/logger.js';
import { getProvider } from './whatsapp/index.js';
import { handleInbound } from './handler.js';
import { listSubscribers } from './store/sessions.js';

export function createServer() {
  const app = express();
  app.disable('x-powered-by');

  // Keep the raw body around: Meta's signature is computed over the exact bytes.
  app.use(
    express.json({
      limit: '1mb',
      verify: (req, _res, buf) => {
        req.rawBody = buf;
      },
    }),
  );
  app.use(express.urlencoded({ extended: false }));

  app.get('/health', (_req, res) => {
    res.json({
      status: 'ok',
      provider: config.provider,
      model: config.ai.model,
      subscribers: listSubscribers().length,
      uptimeSeconds: Math.round(process.uptime()),
    });
  });

  app.get('/', (_req, res) => {
    res.type('text/plain').send('WhatsApp Political Agent is running. Webhook: /webhook');
  });

  // Meta's one-time webhook verification handshake.
  app.get('/webhook', (req, res) => {
    const mode = req.query['hub.mode'];
    const token = req.query['hub.verify_token'];
    const challenge = req.query['hub.challenge'];
    if (mode === 'subscribe' && token && token === config.meta.verifyToken) {
      logger.info('تم التحقق من الويبهوك بنجاح');
      return res.status(200).send(String(challenge ?? ''));
    }
    logger.warn('فشل التحقق من الويبهوك');
    return res.sendStatus(403);
  });

  app.post('/webhook', (req, res) => {
    const provider = getProvider();

    if (provider.name === 'meta') {
      const signature = req.get('x-hub-signature-256');
      if (!provider.verifySignature(req.rawBody ?? Buffer.from(''), signature)) {
        logger.warn('توقيع ويبهوك غير صالح');
        return res.sendStatus(403);
      }
    } else if (config.twilio.validateSignature) {
      const signature = req.get('x-twilio-signature');
      if (!provider.verifySignature(config.twilio.webhookUrl, req.body, signature)) {
        logger.warn('توقيع Twilio غير صالح');
        return res.sendStatus(403);
      }
    }

    // Acknowledge immediately; WhatsApp retries anything slower than a few seconds.
    res.sendStatus(200);

    let messages = [];
    try {
      messages = provider.parseWebhook(req.body) ?? [];
    } catch (error) {
      logger.error('تعذر تحليل محتوى الويبهوك', { error: error.message });
      return undefined;
    }
    if (messages.length) handleInbound(messages, provider);
    return undefined;
  });

  app.use((error, _req, res, _next) => {
    logger.error('خطأ غير متوقع في الخادم', { error: error.message });
    res.sendStatus(500);
  });

  return app;
}
