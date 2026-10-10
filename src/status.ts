import { config } from "./config.js";
import { loadState } from "./store.js";
import { Trader } from "./trader.js";
import { getSolBalance, loadWallet } from "./wallet.js";

const state = loadState();
const wallet = loadWallet();
const trader = new Trader(state, wallet);

console.log(`Mode: ${config.dryRun ? "PAPER" : "LIVE"}`);
if (config.dryRun) console.log(`Paper SOL: ${state.paperSol.toFixed(4)}`);
if (wallet) console.log(`Wallet: ${wallet.publicKey.toBase58()}  ${(await getSolBalance(wallet.publicKey)).toFixed(4)} SOL`);
console.log(`Realized today: ${state.daily.realizedSol.toFixed(4)} SOL | total: ${state.totalRealizedSol.toFixed(4)} SOL`);
console.log(`Open positions (${state.positions.length}):`);
for (const p of state.positions) {
  const v = await trader.valueSol(p).catch(() => NaN);
  const mins = ((Date.now() - p.openedAt) / 60_000).toFixed(0);
  console.log(`  ${p.symbol.padEnd(10)} in ${p.entrySol} SOL  now ${v.toFixed(4)} SOL (${((v / p.entrySol - 1) * 100).toFixed(1)}%)  ${mins}m  ${p.mint}`);
}
