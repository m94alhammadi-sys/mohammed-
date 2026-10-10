import { fetchJson, log } from "./log.js";

const BASE = "https://api.dexscreener.com";

export interface DexPair {
  chainId: string;
  dexId: string;
  pairAddress: string;
  baseToken: { address: string; name: string; symbol: string };
  quoteToken: { address: string; symbol: string };
  priceUsd?: string;
  txns?: Record<string, { buys: number; sells: number }>;
  volume?: Record<string, number>;
  priceChange?: Record<string, number>;
  liquidity?: { usd?: number };
  fdv?: number;
  marketCap?: number;
  pairCreatedAt?: number;
}

interface TokenListing {
  chainId: string;
  tokenAddress: string;
}

/** Collects candidate Solana token addresses from DexScreener's boosted + newest-profile feeds. */
export async function fetchCandidateMints(): Promise<string[]> {
  const feeds = [
    `${BASE}/token-boosts/latest/v1`,
    `${BASE}/token-boosts/top/v1`,
    `${BASE}/token-profiles/latest/v1`,
  ];
  const results = await Promise.allSettled(feeds.map((u) => fetchJson<TokenListing[]>(u)));
  if (results.every((r) => r.status === "rejected")) {
    log.warn(`DexScreener unreachable: ${(results[0] as PromiseRejectedResult).reason}`);
  }
  const mints = new Set<string>();
  for (const r of results) {
    if (r.status !== "fulfilled" || !Array.isArray(r.value)) continue;
    for (const t of r.value) if (t.chainId === "solana" && t.tokenAddress) mints.add(t.tokenAddress);
  }
  return [...mints];
}

/** Returns the most liquid pair for each mint (DexScreener allows 30 addresses per call). */
export async function fetchBestPairs(mints: string[]): Promise<DexPair[]> {
  const best = new Map<string, DexPair>();
  for (let i = 0; i < mints.length; i += 30) {
    const chunk = mints.slice(i, i + 30);
    const pairs = await fetchJson<DexPair[]>(`${BASE}/tokens/v1/solana/${chunk.join(",")}`).catch(() => []);
    for (const p of pairs) {
      if (p.chainId !== "solana") continue;
      const mint = p.baseToken.address;
      const prev = best.get(mint);
      if (!prev || (p.liquidity?.usd ?? 0) > (prev.liquidity?.usd ?? 0)) best.set(mint, p);
    }
  }
  return [...best.values()];
}
