import { config } from "./config.js";
import type { DexPair } from "./dexscreener.js";

export interface Candidate {
  pair: DexPair;
  score: number;
}

/** Applies the market filters from .env; returns why a pair was rejected, or null if it passes. */
export function rejectReason(p: DexPair, now = Date.now()): string | null {
  const c = config;
  if (c.blacklist.has(p.baseToken.address)) return "blacklisted";
  if (p.quoteToken.symbol !== "SOL" && p.quoteToken.symbol !== "USDC") return "quote not SOL/USDC";
  const liq = p.liquidity?.usd ?? 0;
  if (liq < c.minLiquidityUsd) return `liquidity $${liq.toFixed(0)} too low`;
  if (liq > c.maxLiquidityUsd) return "liquidity too high (not a meme play)";
  const volH1 = p.volume?.h1 ?? 0;
  if (volH1 < c.minVolumeH1Usd) return `1h volume $${volH1.toFixed(0)} too low`;
  if (!p.pairCreatedAt) return "unknown pair age";
  const ageMin = (now - p.pairCreatedAt) / 60_000;
  if (ageMin < c.minPairAgeMinutes) return `too new (${ageMin.toFixed(0)}m)`;
  if (ageMin > c.maxPairAgeMinutes) return "too old";
  if ((p.fdv ?? 0) > c.maxFdvUsd) return "FDV too high";
  const h1 = p.txns?.h1 ?? { buys: 0, sells: 0 };
  const ratio = h1.buys / Math.max(1, h1.sells);
  if (ratio < c.minBuySellRatio) return `buy/sell ratio ${ratio.toFixed(2)} too low`;
  const ch1 = p.priceChange?.h1 ?? 0;
  if (ch1 < c.minPriceChangeH1Pct) return `1h change ${ch1}% too low`;
  if (ch1 > c.maxPriceChangeH1Pct) return `1h change ${ch1}% too high (chasing top)`;
  // Falling hard in the last 5 minutes = momentum already gone.
  if ((p.priceChange?.m5 ?? 0) < -10) return "dumping in last 5m";
  return null;
}

/** Momentum score: favours volume relative to liquidity, buy pressure and steady (not parabolic) gains. */
export function score(p: DexPair): number {
  const liq = Math.max(1, p.liquidity?.usd ?? 1);
  const turnover = (p.volume?.h1 ?? 0) / liq;
  const h1 = p.txns?.h1 ?? { buys: 0, sells: 0 };
  const ratio = h1.buys / Math.max(1, h1.sells);
  const ch1 = p.priceChange?.h1 ?? 0;
  const m5 = p.priceChange?.m5 ?? 0;
  return turnover * 2 + Math.min(ratio, 3) + Math.min(ch1, 100) / 50 + Math.max(-1, Math.min(m5, 20) / 10);
}

export function rankCandidates(pairs: DexPair[], exclude: Set<string>): Candidate[] {
  return pairs
    .filter((p) => !exclude.has(p.baseToken.address) && rejectReason(p) === null)
    .map((pair) => ({ pair, score: score(pair) }))
    .sort((a, b) => b.score - a.score);
}
