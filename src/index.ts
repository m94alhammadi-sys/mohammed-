import { config, validateConfig } from "./config.js";
import { fetchBestPairs, fetchCandidateMints } from "./dexscreener.js";
import { log, sleep } from "./log.js";
import { loadState, saveState } from "./store.js";
import { rankCandidates } from "./strategy.js";
import { Trader } from "./trader.js";
import { getSolBalance, loadWallet } from "./wallet.js";

const MAX_CANDIDATES_PER_CYCLE = 5;

async function managePositions(trader: Trader, state: ReturnType<typeof loadState>) {
  for (const pos of [...state.positions]) {
    try {
      const value = await trader.valueSol(pos);
      pos.lastValueSol = value;
      if (value > pos.peakValueSol) pos.peakValueSol = value;
      const reason = trader.exitReason(pos, value);
      if (reason) await trader.sell(pos, reason);
      else log.info(`hold ${pos.symbol}: ${value.toFixed(4)} SOL (${((value / pos.entrySol - 1) * 100).toFixed(1)}%)`);
    } catch (e) {
      log.error(`position ${pos.symbol}: ${(e as Error).message}`);
    }
    saveState(state);
  }
}

async function lookForEntries(trader: Trader, state: ReturnType<typeof loadState>) {
  const blocked = await trader.buyBlockedReason();
  if (blocked) {
    log.info(`not buying: ${blocked}`);
    return;
  }
  const mints = await fetchCandidateMints();
  const pairs = await fetchBestPairs(mints);
  const exclude = new Set([...state.positions.map((p) => p.mint), ...Object.keys(state.cooldown)]);
  const ranked = rankCandidates(pairs, exclude);
  log.info(`scanned ${pairs.length} tokens, ${ranked.length} passed filters`);

  for (const c of ranked.slice(0, MAX_CANDIDATES_PER_CYCLE)) {
    try {
      if (await trader.tryBuy(c.pair)) break; // one buy per cycle
    } catch (e) {
      log.error(`buy ${c.pair.baseToken.symbol}: ${(e as Error).message}`);
      state.cooldown[c.pair.baseToken.address] = Date.now() + 30 * 60_000;
    }
  }
  saveState(state);
}

async function main() {
  validateConfig();
  const wallet = loadWallet();
  const state = loadState();
  const trader = new Trader(state, wallet);

  log.info(`Meme-coin agent starting in ${config.dryRun ? "PAPER (DRY_RUN)" : "🔴 LIVE"} mode`);
  if (wallet) log.info(`wallet ${wallet.publicKey.toBase58()}  balance ${(await getSolBalance(wallet.publicKey)).toFixed(4)} SOL`);
  if (config.dryRun) log.info(`paper balance ${state.paperSol.toFixed(4)} SOL`);
  if (!config.dryRun) {
    log.warn("LIVE trading with real funds. Ctrl+C within 10s to abort.");
    await sleep(10_000);
  }

  let stopping = false;
  process.on("SIGINT", () => {
    if (stopping) process.exit(1);
    stopping = true;
    log.info("stopping after this cycle (open positions are kept; run `npm run panic` to sell all)");
  });

  while (!stopping) {
    try {
      await managePositions(trader, state);
      if (!stopping) await lookForEntries(trader, state);
    } catch (e) {
      log.error(`cycle: ${(e as Error).message}`);
    }
    saveState(state);
    const pnl = state.daily.realizedSol;
    log.info(`— open ${state.positions.length} | today ${pnl >= 0 ? "+" : ""}${pnl.toFixed(4)} SOL | total ${state.totalRealizedSol.toFixed(4)} SOL`);
    for (let i = 0; i < config.pollIntervalSeconds && !stopping; i++) await sleep(1000);
  }
  saveState(state);
}

main().catch((e) => {
  log.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
