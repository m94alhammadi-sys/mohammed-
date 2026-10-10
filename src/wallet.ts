import { Connection, Keypair, PublicKey } from "@solana/web3.js";
import bs58 from "bs58";
import { config, LAMPORTS_PER_SOL } from "./config.js";

export const connection = new Connection(config.rpcUrl, "confirmed");

export function loadWallet(): Keypair | null {
  if (!config.privateKey) return null;
  const key = config.privateKey;
  // Phantom exports Base58; also accept a JSON byte array (solana-keygen format).
  const secret = key.startsWith("[") ? Uint8Array.from(JSON.parse(key)) : bs58.decode(key);
  return Keypair.fromSecretKey(secret);
}

export async function getSolBalance(owner: PublicKey): Promise<number> {
  return (await connection.getBalance(owner)) / LAMPORTS_PER_SOL;
}

/** Raw (integer) token balance of `mint` held by `owner`, summed over all token accounts. */
export async function getTokenBalanceRaw(owner: PublicKey, mint: string): Promise<bigint> {
  const res = await connection.getParsedTokenAccountsByOwner(owner, { mint: new PublicKey(mint) });
  let total = 0n;
  for (const acc of res.value) total += BigInt(acc.account.data.parsed.info.tokenAmount.amount);
  return total;
}
