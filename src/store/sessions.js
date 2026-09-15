import path from 'node:path';
import { config, normalizePhone } from '../config.js';
import { JsonStore } from './jsonStore.js';

const store = new JsonStore(path.join(config.dataDir, 'sessions.json'), {
  initial: { users: {}, processedMessages: [] },
});

const MAX_PROCESSED_IDS = 500;

function blankUser(phone) {
  return {
    phone,
    name: '',
    createdAt: new Date().toISOString(),
    lastSeenAt: null,
    subscribed: config.briefing.defaultSubscribers.includes(normalizePhone(phone)),
    history: [],
    hits: [],
    messageCount: 0,
  };
}

export function getUser(phone) {
  const key = normalizePhone(phone);
  const users = store.get('users', {});
  if (!users[key]) {
    users[key] = blankUser(key);
    store.set('users', users);
  }
  return users[key];
}

export function saveUser(user) {
  const users = store.get('users', {});
  users[normalizePhone(user.phone)] = user;
  store.set('users', users);
  return user;
}

export function listUsers() {
  return Object.values(store.get('users', {}));
}

export function listSubscribers() {
  const fromUsers = listUsers()
    .filter((user) => user.subscribed)
    .map((user) => user.phone);
  return [...new Set([...config.briefing.defaultSubscribers, ...fromUsers])].filter(Boolean);
}

export function setSubscribed(phone, subscribed) {
  const user = getUser(phone);
  user.subscribed = subscribed;
  saveUser(user);
  return user;
}

export function touchUser(phone, name) {
  const user = getUser(phone);
  user.lastSeenAt = new Date().toISOString();
  user.messageCount += 1;
  if (name && !user.name) user.name = name;
  saveUser(user);
  return user;
}

/**
 * Conversation history in Anthropic message format. Only the last
 * `historyTurns` entries are replayed, so an old chat never grows unbounded.
 */
export function getHistory(phone) {
  return getUser(phone).history ?? [];
}

export function appendHistory(phone, messages) {
  const user = getUser(phone);
  user.history = [...(user.history ?? []), ...messages].slice(-config.ai.historyTurns * 2);
  saveUser(user);
  return user.history;
}

export function clearHistory(phone) {
  const user = getUser(phone);
  user.history = [];
  saveUser(user);
}

/** Sliding-window rate limit: how many messages this number sent in the last hour. */
export function checkRateLimit(phone, { limit = config.limits.messagesPerHour } = {}) {
  const user = getUser(phone);
  const cutoff = Date.now() - 60 * 60 * 1000;
  const hits = (user.hits ?? []).filter((at) => at > cutoff);
  if (hits.length >= limit) {
    const retryAfterMs = Math.max(0, hits[0] + 60 * 60 * 1000 - Date.now());
    user.hits = hits;
    saveUser(user);
    return { allowed: false, remaining: 0, retryAfterMs };
  }
  hits.push(Date.now());
  user.hits = hits;
  saveUser(user);
  return { allowed: true, remaining: limit - hits.length, retryAfterMs: 0 };
}

/** WhatsApp retries webhook deliveries, so every message id is handled once. */
export function isDuplicate(messageId) {
  if (!messageId) return false;
  const seen = store.get('processedMessages', []);
  if (seen.includes(messageId)) return true;
  seen.push(messageId);
  store.set('processedMessages', seen.slice(-MAX_PROCESSED_IDS));
  return false;
}

export async function flushSessions() {
  await store.flush();
}

export const __store = store;
