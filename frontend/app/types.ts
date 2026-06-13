export interface User {
  user_id: string;
  balance: number;
  open_markets?: number;
  resolved_markets?: number;
}

export interface Market {
  id: string;
  title: string;
  status: string;
  current_prices: [number, number];
  current_b: number;
  is_adaptive: boolean;
  total_trades: number;
  total_fees_earned: number;
  fee_rate?: number;
  resolution_outcome?: string | null;
  market_maker_pl?: number | null;
  liquidity_alpha?: number | null;
  liquidity_min_b?: number | null;
  liquidity_max_b?: number | null;
}

export interface ActivityItem {
  id: string;
  market_id: string;
  market_title: string;
  user_id: string;
  shares_yes: number;
  shares_no: number;
  effective_cost: number;
  fee: number;
  price_after_yes: number;
  price_after_no: number;
  timestamp?: string;
}

export interface Account {
  user_id: string;
  cash_balance: number;
  position_value: number;
  total_value: number;
}

export interface Portfolio {
  user_id: string;
  balance: number;
  positions: Record<string, { yes: number; no: number; total: number; value?: number }>;
  realized_pnl: number;
  total_payouts_received: number;
  open_markets_count: number;
  resolved_markets_count: number;
}

export interface LeaderboardEntry {
  user_id: string;
  resolved_trades: number;
  avg_brier?: number;
  avg_log_score?: number;
  total_pnl: number;
}

export type LeaderboardMetric = 'brier' | 'log' | 'pnl';

export interface Trade {
  id?: string;
  user_id?: string;
  shares_yes: number;
  shares_no: number;
  effective_cost?: number;
  fee?: number;
  price_after_yes?: number;
  price_after_no?: number;
  timestamp?: string;
  mm_profit?: number;  // running market-maker P/L after this trade (admin chart)
}

export interface MarketDetail extends Market {
  // additional if needed
}

export interface QuoteResponse {
  effective_cost: number;
  raw_cost?: number;
  fee?: number;
  price_after: [number, number];
  impact?: [number, number];
  slippage?: number;
  status?: string;
}

export interface ModalState {
  selectedMarketId: string | null;
  marketDetail: MarketDetail | null;
  marketTrades: Trade[];
  marketPositions: Record<string, { yes: number; no: number }>;
  hoveredTradeIdx: number | null;
  modalTradeAmountYes: number;
  modalTradeAmountNo: number;
  modalQuote: QuoteResponse | null;
}
