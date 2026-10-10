import { validateConfig } from "./config.js";
import { log } from "./log.js";
import { loadState, saveState } from "./store.js";
import { Trader } from "./trader.js";
import { loadWallet } from "./wallet.js";

// Emergency exit: sells every open position tracked by the agent.
validateConfig();
const state = loadState();
const trader = new Trader(state, loadWallet());
log.warn(`selling ${state.positions.length} open position(s)`);
for (const pos of [...state.positions]) {
  try {
    await trader.sell(pos, "panic");
  } catch (e) {
    log.error(`${pos.symbol}: ${(e as Error).message}`);
  }
  saveState(state);
}
