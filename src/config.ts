import "dotenv/config";

function str(name: string, def = ""): string {
  return (process.env[name] ?? def).trim();
}
function num(name: string, def: number): number {
  const raw = str(name);
  if (raw === "") return def;
  const n = Number(raw.split("#")[0].trim());
  if (!Number.isFinite(n)) throw new Error(`Config ${name} must be a number, got "${raw}"`);
  return n;
}
function bool(name: string, def: boolean): boolean {
  const raw = str(name).split("#")[0].trim().toLowerCase();
  if (raw === "") return def;
  return ["1", "true", "yes", "on"].includes(raw);
}

export const SOL_MINT = "So11111111111111111111111111111111111111112";
export const LAMPORTS_PER_SOL = 1_000_000_000;

export const config = {
  dryRun: bool("DRY_RUN", true),
  paperStartSol: num("PAPER_START_SOL", 1),
  privateKey: str("PRIVATE_KEY"),
  rpcUrl: str("RPC_URL", "https://api.mainnet-beta.solana.com"),

  buyAmountSol: num("BUY_AMOUNT_SOL", 0.05),
  maxOpenPositions: num("MAX_OPEN_POSITIONS", 3),
  maxTotalExposureSol: num("MAX_TOTAL_EXPOSURE_SOL", 0.2),
  minSolReserve: num("MIN_SOL_RESERVE", 0.05),
  dailyLossLimitSol: num("DAILY_LOSS_LIMIT_SOL", 0.1),
  slippageBps: num("SLIPPAGE_BPS", 1500),
  maxPriceImpactPct: num("MAX_PRICE_IMPACT_PCT", 5),
  priorityFeeMaxLamports: num("PRIORITY_FEE_MAX_LAMPORTS", 200_000),

  takeProfitPct: num("TAKE_PROFIT_PCT", 50),
  stopLossPct: num("STOP_LOSS_PCT", 20),
  trailingStopPct: num("TRAILING_STOP_PCT", 15),
  trailingActivationPct: num("TRAILING_ACTIVATION_PCT", 20),
  maxHoldMinutes: num("MAX_HOLD_MINUTES", 60),

  minLiquidityUsd: num("MIN_LIQUIDITY_USD", 20_000),
  maxLiquidityUsd: num("MAX_LIQUIDITY_USD", 2_000_000),
  minVolumeH1Usd: num("MIN_VOLUME_H1_USD", 20_000),
  minPairAgeMinutes: num("MIN_PAIR_AGE_MINUTES", 30),
  maxPairAgeMinutes: num("MAX_PAIR_AGE_MINUTES", 4320),
  maxFdvUsd: num("MAX_FDV_USD", 20_000_000),
  minBuySellRatio: num("MIN_BUY_SELL_RATIO", 1.2),
  minPriceChangeH1Pct: num("MIN_PRICE_CHANGE_H1_PCT", 5),
  maxPriceChangeH1Pct: num("MAX_PRICE_CHANGE_H1_PCT", 300),

  requireNoMintAuthority: bool("REQUIRE_NO_MINT_AUTHORITY", true),
  requireNoFreezeAuthority: bool("REQUIRE_NO_FREEZE_AUTHORITY", true),
  useRugcheck: bool("USE_RUGCHECK", true),
  rugcheckMaxScore: num("RUGCHECK_MAX_SCORE", 1000),
  blacklist: new Set(
    str("BLACKLIST").split("#")[0].split(",").map((s) => s.trim()).filter(Boolean),
  ),

  pollIntervalSeconds: num("POLL_INTERVAL_SECONDS", 20),
  jupiterApi: str("JUPITER_API", "https://lite-api.jup.ag/swap/v1").replace(/\/$/, ""),
};

export type Config = typeof config;

export function validateConfig(): void {
  if (!config.dryRun && !config.privateKey) {
    throw new Error("DRY_RUN=false requires PRIVATE_KEY in .env");
  }
  if (config.buyAmountSol <= 0) throw new Error("BUY_AMOUNT_SOL must be > 0");
  if (config.stopLossPct <= 0 || config.stopLossPct >= 100) {
    throw new Error("STOP_LOSS_PCT must be between 0 and 100");
  }
  if (config.buyAmountSol > config.maxTotalExposureSol) {
    throw new Error("BUY_AMOUNT_SOL cannot exceed MAX_TOTAL_EXPOSURE_SOL");
  }
}
