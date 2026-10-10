import { Connection, PublicKey, type ParsedAccountData } from "@solana/web3.js";
import { config } from "./config.js";
import { fetchJson } from "./log.js";

export interface SafetyResult {
  ok: boolean;
  reasons: string[];
  decimals?: number;
}

interface RugcheckSummary {
  score?: number;
  score_normalised?: number;
  risks?: { name: string; level: string }[];
}

/** On-chain + rugcheck.xyz checks. Fails closed: if a check can't run, the token is rejected. */
export async function checkTokenSafety(conn: Connection, mint: string): Promise<SafetyResult> {
  const reasons: string[] = [];
  let decimals: number | undefined;

  try {
    const info = await conn.getParsedAccountInfo(new PublicKey(mint));
    const data = info.value?.data as ParsedAccountData | undefined;
    const parsed = data?.parsed?.info;
    if (!parsed) {
      reasons.push("mint account not found / not parsable");
    } else {
      decimals = parsed.decimals;
      if (config.requireNoMintAuthority && parsed.mintAuthority) reasons.push("mint authority still enabled");
      if (config.requireNoFreezeAuthority && parsed.freezeAuthority) reasons.push("freeze authority enabled");
      if (data.program === "spl-token-2022") {
        const exts: { extension: string }[] = parsed.extensions ?? [];
        const bad = exts.map((e) => e.extension).filter((e) =>
          ["transferFeeConfig", "permanentDelegate", "transferHook", "nonTransferable", "pausableConfig"].includes(e),
        );
        if (bad.length) reasons.push(`risky token-2022 extensions: ${bad.join(", ")}`);
      }
    }
  } catch (e) {
    reasons.push(`on-chain check failed: ${(e as Error).message}`);
  }

  if (config.useRugcheck) {
    try {
      const r = await fetchJson<RugcheckSummary>(`https://api.rugcheck.xyz/v1/tokens/${mint}/report/summary`);
      const dangers = (r.risks ?? []).filter((x) => x.level === "danger").map((x) => x.name);
      if (dangers.length) reasons.push(`rugcheck danger: ${dangers.join(", ")}`);
      if ((r.score ?? 0) > config.rugcheckMaxScore) reasons.push(`rugcheck score ${r.score} > ${config.rugcheckMaxScore}`);
    } catch (e) {
      reasons.push(`rugcheck unavailable: ${(e as Error).message}`);
    }
  }

  return { ok: reasons.length === 0, reasons, decimals };
}
