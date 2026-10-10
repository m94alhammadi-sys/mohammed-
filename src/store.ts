import fs from "node:fs";
import path from "node:path";
import { config } from "./config.js";

const DATA_DIR = path.resolve("data");
const STATE_FILE = path.join(DATA_DIR, "state.json");
const TRADES_FILE = path.join(DATA_DIR, "trades.csv");

export interface Position {
  mint: string;
  symbol: string;
  entrySol: number;
  tokenAmountRaw: string;
  openedAt: number;
  peakValueSol: number;
  lastValueSol: number;
  buySig: string;
}

export interface State {
  mode: "paper" | "live";
  paperSol: number;
  positions: Position[];
  daily: { date: string; realizedSol: number };
  totalRealizedSol: number;
  /** mint -> timestamp until which it must not be bought again */
  cooldown: Record<string, number>;
}

const today = () => new Date().toISOString().slice(0, 10);

function fresh(): State {
  return {
    mode: config.dryRun ? "paper" : "live",
    paperSol: config.paperStartSol,
    positions: [],
    daily: { date: today(), realizedSol: 0 },
    totalRealizedSol: 0,
    cooldown: {},
  };
}

export function loadState(): State {
  const mode = config.dryRun ? "paper" : "live";
  const file = STATE_FILE.replace(".json", `.${mode}.json`);
  if (!fs.existsSync(file)) return fresh();
  const s = JSON.parse(fs.readFileSync(file, "utf8")) as State;
  if (s.daily.date !== today()) s.daily = { date: today(), realizedSol: 0 };
  const now = Date.now();
  for (const [m, until] of Object.entries(s.cooldown)) if (until < now) delete s.cooldown[m];
  return s;
}

export function saveState(s: State): void {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const file = STATE_FILE.replace(".json", `.${s.mode}.json`);
  fs.writeFileSync(file + ".tmp", JSON.stringify(s, null, 2));
  fs.renameSync(file + ".tmp", file);
}

export function recordTrade(row: {
  mode: string; side: "BUY" | "SELL"; symbol: string; mint: string;
  sol: number; pnlSol?: number; reason?: string; sig: string;
}): void {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(TRADES_FILE)) {
    fs.writeFileSync(TRADES_FILE, "time,mode,side,symbol,mint,sol,pnl_sol,reason,signature\n");
  }
  const cells = [
    new Date().toISOString(), row.mode, row.side, row.symbol, row.mint,
    row.sol.toFixed(6), row.pnlSol?.toFixed(6) ?? "", row.reason ?? "", row.sig,
  ].map((c) => `"${String(c).replace(/"/g, '""')}"`);
  fs.appendFileSync(TRADES_FILE, cells.join(",") + "\n");
}
