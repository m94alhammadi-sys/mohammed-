import { Connection, Keypair, VersionedTransaction } from "@solana/web3.js";
import { config } from "./config.js";
import { fetchJson } from "./log.js";

export interface Quote {
  inputMint: string;
  outputMint: string;
  inAmount: string;
  outAmount: string;
  priceImpactPct: string;
  [k: string]: unknown;
}

export async function getQuote(inputMint: string, outputMint: string, amount: bigint): Promise<Quote> {
  const params = new URLSearchParams({
    inputMint,
    outputMint,
    amount: amount.toString(),
    slippageBps: String(config.slippageBps),
  });
  return fetchJson<Quote>(`${config.jupiterApi}/quote?${params}`);
}

export function priceImpactPct(q: Quote): number {
  return Math.abs(Number(q.priceImpactPct ?? 0)) * 100;
}

/** Builds, signs and sends a swap for the given quote; returns the confirmed signature. */
export async function executeSwap(conn: Connection, wallet: Keypair, quote: Quote): Promise<string> {
  const { swapTransaction, lastValidBlockHeight } = await fetchJson<{ swapTransaction: string; lastValidBlockHeight: number }>(`${config.jupiterApi}/swap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      quoteResponse: quote,
      userPublicKey: wallet.publicKey.toBase58(),
      wrapAndUnwrapSol: true,
      dynamicComputeUnitLimit: true,
      dynamicSlippage: true,
      prioritizationFeeLamports: {
        priorityLevelWithMaxLamports: { maxLamports: config.priorityFeeMaxLamports, priorityLevel: "veryHigh" },
      },
    }),
  });

  const tx = VersionedTransaction.deserialize(Buffer.from(swapTransaction, "base64"));
  tx.sign([wallet]);
  const sig = await conn.sendRawTransaction(tx.serialize(), { skipPreflight: false, maxRetries: 3 });
  const res = await conn.confirmTransaction(
    { signature: sig, blockhash: tx.message.recentBlockhash, lastValidBlockHeight },
    "confirmed",
  );
  if (res.value.err) throw new Error(`swap failed on-chain: ${JSON.stringify(res.value.err)} (${sig})`);
  return sig;
}
