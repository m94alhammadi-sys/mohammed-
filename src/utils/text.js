/**
 * WhatsApp rejects text messages longer than 4096 characters, so long answers
 * are split on paragraph -> line -> sentence -> hard-cut boundaries, in that
 * order of preference.
 */
export function chunkText(text, size = 3500) {
  const clean = String(text ?? '').trim();
  if (!clean) return [];
  if (clean.length <= size) return [clean];

  const chunks = [];
  let rest = clean;

  while (rest.length > size) {
    const window = rest.slice(0, size);
    let cut = window.lastIndexOf('\n\n');
    if (cut < size * 0.5) cut = window.lastIndexOf('\n');
    if (cut < size * 0.5) cut = window.lastIndexOf('. ');
    if (cut < size * 0.5) cut = window.lastIndexOf('، ');
    if (cut < size * 0.5) cut = window.lastIndexOf(' ');
    if (cut <= 0) cut = size;
    chunks.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) chunks.push(rest);
  return chunks.filter(Boolean);
}

/** Adds "1/3" markers so a split answer still reads in order on the phone. */
export function numberChunks(chunks) {
  if (chunks.length <= 1) return chunks;
  return chunks.map((chunk, index) => `(${index + 1}/${chunks.length})\n${chunk}`);
}

export function truncate(text, max) {
  const clean = String(text ?? '');
  return clean.length <= max ? clean : `${clean.slice(0, max)}…`;
}

/** Strips zero-width and bidi control characters used to smuggle text. */
export function sanitizeInbound(text) {
  return String(text ?? '')
    .replace(/[​-‏‪-‮⁦-⁩﻿]/g, '')
    .trim();
}

export function stripHtml(html) {
  return String(html ?? '')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

export function formatRelativeTime(date, now = new Date()) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
  const minutes = Math.round((now.getTime() - date.getTime()) / 60000);
  if (minutes < 1) return 'الآن';
  if (minutes < 60) return `قبل ${minutes} دقيقة`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `قبل ${hours} ساعة`;
  const days = Math.round(hours / 24);
  return `قبل ${days} يوم`;
}
