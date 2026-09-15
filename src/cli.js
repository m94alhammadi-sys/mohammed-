#!/usr/bin/env node
/**
 * Local test harness: talk to the agent from the terminal, with no WhatsApp
 * account needed. `npm run chat` for a conversation, `npm run brief` for the
 * daily briefing.
 */
import readline from 'node:readline/promises';
import { stdin, stdout, argv } from 'node:process';
import { config, validateConfig } from './config.js';
import { ask, buildBriefing } from './ai/agent.js';
import { getHeadlines, formatHeadlines } from './news/headlines.js';
import { matchCommand } from './commands.js';

const problems = validateConfig({ requireWhatsApp: false });
if (problems.length) {
  console.error('إعدادات ناقصة:', problems.join('، '));
  process.exit(1);
}

async function runBriefing() {
  const items = await getHeadlines({ limit: 30 });
  const result = await buildBriefing({ headlines: formatHeadlines(items, { withLinks: false }) });
  console.log(`\n${result.text}\n`);
}

async function runChat() {
  const rl = readline.createInterface({ input: stdin, output: stdout });
  let history = [];
  console.log(`محادثة تجريبية مع المستشار السياسي (${config.ai.model}). اكتب "خروج" للإنهاء.\n`);

  for (;;) {
    const input = (await rl.question('أنت: ')).trim();
    if (!input) continue;
    if (['خروج', 'exit', 'quit'].includes(input)) break;

    if (matchCommand(input)?.name === 'reset') {
      history = [];
      console.log('\nالمستشار: تم مسح السياق.\n');
      continue;
    }

    try {
      process.stdout.write('\n… يبحث ويحلل\n');
      const result = await ask({ history, text: input });
      console.log(`\nالمستشار: ${result.text}\n`);
      if (result.sources?.length) {
        console.log('المصادر:');
        for (const source of result.sources.slice(0, 5)) console.log(` - ${source.title}: ${source.url}`);
        console.log('');
      }
      history = [
        ...history,
        { role: 'user', content: input },
        { role: 'assistant', content: result.text },
      ].slice(-config.ai.historyTurns * 2);
    } catch (error) {
      console.error('خطأ:', error.message);
    }
  }
  rl.close();
}

if (argv.includes('--brief')) {
  await runBriefing();
} else if (argv.includes('--news')) {
  const topic = argv[argv.indexOf('--news') + 1] ?? '';
  console.log(formatHeadlines(await getHeadlines({ topic, limit: 15 })));
} else {
  await runChat();
}
