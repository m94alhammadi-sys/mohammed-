import type { Keypair } from "@solana/web3.js";
import { config, LAMPORTS_PER_SOL, SOL_MINT } from "./config.js";
import { executeSwap, getQuote, priceImpactPct } from "./jupiter.js";
import { log, sleep } from "./log.js";
import { checkTokenSafety } from "./safety.js";
import { recordTrade, type Position, type State } from "./store.js";
import { connection, getSolBalance, getTokenBalanceRaw } from "./wallet.js";
import type { DexPair } from "./dexscreener.js";

const COOLDOWN_MS = 6 * 60 * 60 * 1000;
const MAX_ROUND_TRIP_LOSS_PCT = 25;

export class Trader {
  constructor(private state: State, private wallet: Keypair | null) {}

  get mode() {
    return config.dryRun ? "paper" : "live";
  }

  exposureSol(): number {
    return this.state.positions.reduce((s, p) => s + p.entrySol, 0);
  }

  async availableSol(): Promise<number> {
    if (config.dryRun) return this.state.paperSol;
    return getSolBalance(this.wallet!.publicKey);
  }

  /** Returns null if a new buy is allowed, otherwise the reason it is blocked. */
  async buyBlockedReason(): Promise<string | null> {
    if (this.state.daily.realizedSol <= -config.dailyLossLimitSol) {
      return `daily loss limit hit (${this.state.daily.realizedSol.toFixed(4)} SOL)`;
    }
    if (this.state.positions.length >= config.maxOpenPositions) return "max open positions";
    if (this.exposureSol() + config.buyAmountSol > config.maxTotalExposureSol + 1e-9) return "max exposure";
    const avail = await this.availableSol();
    if (avail - config.buyAmountSol < config.minSolReserve) return `low SOL balance (${avail.toFixed(4)})`;
    return null;
  }

  /** Runs safety + liquidity checks and buys. Returns true if a position was opened. */
  async tryBuy(pair: DexPair): Promise<boolean> {
    const mint = pair.baseToken.address;
    const symbol = pair.baseToken.symbol;

    const safety = await checkTokenSafety(connection, mint);
    if (!safety.ok) {
      log.info(`skip ${symbol}: ${safety.reasons.join("; ")}`);
      this.state.cooldown[mint] = Date.now() + COOLDOWN_MS;
      return false;
    }

    const lamports = BigInt(Math.floor(config.buyAmountSol * LAMPORTS_PER_SOL));
    const buyQuote = await getQuote(SOL_MINT, mint, lamports);
    const impact = priceImpactPct(buyQuote);
    if (impact > config.maxPriceImpactPct) {
      log.info(`skip ${symbol}: price impact ${impact.toFixed(2)}%`);
      return false;
    }

    // Honeypot / thin-exit check: can we actually sell what we'd receive, and at what loss?
    try {
      const back = await getQuote(mint, SOL_MINT, BigInt(buyQuote.outAmount));
      const roundTripLoss = (1 - Number(back.outAmount) / Number(lamports)) * 100;
      if (roundTripLoss > MAX_ROUND_TRIP_LOSS_PCT) {
        log.info(`skip ${symbol}: round-trip loss ${roundTripLoss.toFixed(1)}%`);
        this.state.cooldown[mint] = Date.now() + COOLDOWN_MS;
        return false;
      }
    } catch {
      log.info(`skip ${symbol}: no sell route (possible honeypot)`);
      this.state.cooldown[mint] = Date.now() + COOLDOWN_MS;
      return false;
    }

    let sig = "paper";
    let tokenAmountRaw = BigInt(buyQuote.outAmount);
    if (config.dryRun) {
      this.state.paperSol -= config.buyAmountSol;
    } else {
      const before = await getTokenBalanceRaw(this.wallet!.publicKey, mint);
      sig = await executeSwap(connection, this.wallet!, buyQuote);
      tokenAmountRaw = await this.waitForBalanceChange(mint, before);
    }

    const pos: Position = {
      mint, symbol,
      entrySol: config.buyAmountSol,
      tokenAmountRaw: tokenAmountRaw.toString(),
      openedAt: Date.now(),
      peakValueSol: config.buyAmountSol,
      lastValueSol: config.buyAmountSol,
      buySig: sig,
    };
    this.state.positions.push(pos);
    this.state.cooldown[mint] = Date.now() + COOLDOWN_MS;
    recordTrade({ mode: this.mode, side: "BUY", symbol, mint, sol: pos.entrySol, sig });
    log.trade(`BUY ${symbol} for ${pos.entrySol} SOL  ${pair.priceUsd ? "@ $" + pair.priceUsd : ""}  ${sig}`);
    return true;
  }

  private async waitForBalanceChange(mint: string, before: bigint): Promise<bigint> {
    for (let i = 0; i < 10; i++) {
      const now = await getTokenBalanceRaw(this.wallet!.publicKey, mint);
      if (now > before) return now - before;
      await sleep(1500);
    }
    throw new Error(`bought ${mint} but token balance did not update`);
  }

  /** Current value of the position in SOL, from a real sell quote (includes slippage/impact). */
  async valueSol(pos: Position): Promise<number> {
    const q = await getQuote(pos.mint, SOL_MINT, BigInt(pos.tokenAmountRaw));
    return Number(q.outAmount) / LAMPORTS_PER_SOL;
  }

  exitReason(pos: Position, value: number): string | null {
    const pnlPct = (value / pos.entrySol - 1) * 100;
    const peakPct = (pos.peakValueSol / pos.entrySol - 1) * 100;
    const fromPeakPct = (1 - value / pos.peakValueSol) * 100;
    if (pnlPct >= config.takeProfitPct) return `take-profit ${pnlPct.toFixed(1)}%`;
    if (pnlPct <= -config.stopLossPct) return `stop-loss ${pnlPct.toFixed(1)}%`;
    if (peakPct >= config.trailingActivationPct && fromPeakPct >= config.trailingStopPct) {
      return `trailing-stop (peak +${peakPct.toFixed(1)}%, now ${pnlPct.toFixed(1)}%)`;
    }
    if (Date.now() - pos.openedAt > config.maxHoldMinutes * 60_000) return `max hold time (${pnlPct.toFixed(1)}%)`;
    return null;
  }

  async sell(pos: Position, reason: string): Promise<void> {
    let amount = BigInt(pos.tokenAmountRaw);
    if (!config.dryRun) {
      const held = await getTokenBalanceRaw(this.wallet!.publicKey, pos.mint);
      if (held < amount) amount = held;
    }
    let outSol = 0;
    let sig = "paper";
    if (amount > 0n) {
      const q = await getQuote(pos.mint, SOL_MINT, amount);
      outSol = Number(q.outAmount) / LAMPORTS_PER_SOL;
      if (config.dryRun) this.state.paperSol += outSol;
      else sig = await executeSwap(connection, this.wallet!, q);
    }
    const pnl = outSol - pos.entrySol;
    this.state.positions = this.state.positions.filter((p) => p.mint !== pos.mint);
    this.state.daily.realizedSol += pnl;
    this.state.totalRealizedSol += pnl;
    recordTrade({ mode: this.mode, side: "SELL", symbol: pos.symbol, mint: pos.mint, sol: outSol, pnlSol: pnl, reason, sig });
    log.trade(`SELL ${pos.symbol} -> ${outSol.toFixed(4)} SOL  PnL ${pnl >= 0 ? "+" : ""}${pnl.toFixed(4)} SOL  [${reason}]  ${sig}`);
  }
}
