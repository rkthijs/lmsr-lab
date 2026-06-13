"use client";

import React from 'react';
import PriceHistoryChart from './PriceHistoryChart';
import { MarketDetail, Trade, LeaderboardMetric, QuoteResponse } from '../types';

interface MarketModalProps {
  selectedMarketId: string | null;
  marketDetail: MarketDetail | null;
  marketTrades: Trade[];
  marketPositions: Record<string, { yes: number; no: number }>;
  hoveredTradeIdx: number | null;
  setHoveredTradeIdx: (idx: number | null) => void;
  modalTradeAmountYes: number;
  setModalTradeAmountYes: (val: number) => void;
  modalTradeAmountNo: number;
  setModalTradeAmountNo: (val: number) => void;
  modalQuote: QuoteResponse | null;
  setModalQuote: (q: QuoteResponse | null) => void;
  activeTab: 'user' | 'admin';
  selectedUser: string;
  resolveOutcome: 'yes' | 'no';
  setResolveOutcome: (o: 'yes' | 'no') => void;
  onClose: () => void;
  onTrade: () => void;
  onRefresh: () => void;
  onResolve: (marketId: string, outcome: 'yes' | 'no') => Promise<void> | void;
  onLoadAdminPositions: (marketId: string) => void;
  onUpdateQuote: (yes: number, no: number) => void;
}

export default function MarketModal({
  selectedMarketId,
  marketDetail,
  marketTrades,
  marketPositions,
  hoveredTradeIdx,
  setHoveredTradeIdx,
  modalTradeAmountYes,
  setModalTradeAmountYes,
  modalTradeAmountNo,
  setModalTradeAmountNo,
  modalQuote,
  setModalQuote,
  activeTab,
  selectedUser,
  resolveOutcome,
  setResolveOutcome,
  onClose,
  onTrade,
  onRefresh,
  onResolve,
  onLoadAdminPositions,
  onUpdateQuote,
}: MarketModalProps) {
  if (!selectedMarketId) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/70 p-4 pt-12 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl rounded-3xl bg-zinc-950 border border-zinc-700 text-white shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <div>
            <div className="font-semibold text-2xl tracking-tight">
              {marketDetail?.title || 'Market View'}
            </div>
            <div className="text-xs text-zinc-400 mt-0.5">
              {marketDetail?.id} • {marketDetail?.status?.toUpperCase()} 
              {marketDetail?.is_adaptive ? ' • Adaptive b' : ''}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {activeTab === 'admin' && (
              <div className="px-3 py-1 text-xs rounded-full bg-red-900/40 text-red-300 border border-red-700">ADMIN VIEW</div>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm rounded-xl border border-zinc-700 hover:bg-zinc-900 transition"
            >
              Close (Esc)
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          {/* Big current prices */}
          {marketDetail && (
            <div className="flex gap-3">
              <div className="flex-1 bg-zinc-900 border border-emerald-500/40 rounded-2xl p-4 text-center">
                <div className="text-xs tracking-[2px] text-emerald-400 font-medium">YES</div>
                <div className="text-5xl font-bold text-emerald-400 tabular-nums mt-1">
                  {(marketDetail.current_prices?.[0] * 100 || 50).toFixed(1)}<span className="text-2xl align-super">¢</span>
                </div>
              </div>
              <div className="flex-1 bg-zinc-900 border border-red-500/40 rounded-2xl p-4 text-center">
                <div className="text-xs tracking-[2px] text-red-400 font-medium">NO</div>
                <div className="text-5xl font-bold text-red-400 tabular-nums mt-1">
                  {(marketDetail.current_prices?.[1] * 100 || 50).toFixed(1)}<span className="text-2xl align-super">¢</span>
                </div>
              </div>
            </div>
          )}

          {/* Key metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3">
              <div className="text-zinc-400 text-xs">Current Liquidity b</div>
              <div className="font-semibold text-lg">{marketDetail?.current_b?.toFixed(1) ?? '—'}</div>
              {marketDetail?.is_adaptive && (
                <div className="text-[10px] text-emerald-400">adaptive</div>
              )}
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3">
              <div className="text-zinc-400 text-xs">Total Trades</div>
              <div className="font-semibold text-lg">{marketDetail?.total_trades ?? marketTrades.length}</div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3">
              <div className="text-zinc-400 text-xs">Fees Earned</div>
              <div className="font-semibold text-lg tabular-nums">{(marketDetail?.total_fees_earned ?? 0).toFixed(2)}</div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-3">
              <div className="text-zinc-400 text-xs">Fee Rate</div>
              <div className="font-semibold text-lg">{((marketDetail?.fee_rate ?? 0.025) * 100).toFixed(1)}%</div>
            </div>
          </div>

          {/* TIME SERIES */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold text-lg">Price History — P(Yes)</div>
              <div className="text-xs text-zinc-400">Y-axis fixed 0 → 1.0 (like Streamlit TRADE tab)</div>
            </div>

            <PriceHistoryChart
              trades={marketTrades}
              hoveredIdx={hoveredTradeIdx}
              onHover={setHoveredTradeIdx}
            />
          </div>

          {/* Recent trades table */}
          <div>
            <div className="font-semibold mb-2">Recent Trades</div>
            {marketTrades.length === 0 ? (
              <div className="text-sm text-zinc-400">No trades recorded yet.</div>
            ) : (
              <div className="max-h-44 overflow-auto border border-zinc-800 rounded-xl bg-zinc-950 text-sm">
                <table className="w-full">
                  <thead className="text-xs text-zinc-400 sticky top-0 bg-zinc-900">
                    <tr>
                      <th className="text-left p-2 pl-3">#</th>
                      <th className="text-left p-2">User</th>
                      <th className="text-right p-2">Yes</th>
                      <th className="text-right p-2">No</th>
                      <th className="text-right p-2 pr-3">Price After (Yes)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {marketTrades.slice(-12).reverse().map((t: any, idx: number) => (
                      <tr key={idx} className="hover:bg-zinc-900/50">
                        <td className="p-2 pl-3 text-zinc-400 tabular-nums">{marketTrades.length - idx}</td>
                        <td className="p-2 font-medium">{t.user_id}</td>
                        <td className="p-2 text-right tabular-nums text-emerald-300">{t.shares_yes}</td>
                        <td className="p-2 text-right tabular-nums text-red-300">{t.shares_no}</td>
                        <td className="p-2 pr-3 text-right tabular-nums font-mono text-emerald-400">
                          {typeof t.price_after_yes === 'number' ? (t.price_after_yes * 100).toFixed(1) + '¢' : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="text-[10px] text-zinc-400 mt-1">Showing latest trades. Price after = market price immediately following this trade.</div>
          </div>

          {/* Focused trading + quote (only for open markets) */}
          {marketDetail?.status === 'open' ? (
            <div className="border-t border-zinc-700 pt-4">
              <div className="font-semibold mb-1">Trade as <span className="text-emerald-400">{selectedUser}</span> on this market</div>
              <div className="flex gap-2 items-end mb-3">
                <div>
                  <div className="text-xs text-emerald-400 mb-1">YES shares</div>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={modalTradeAmountYes}
                    onChange={(e) => setModalTradeAmountYes(Math.max(0, parseInt(e.target.value) || 0))}
                    className="w-28 bg-zinc-900 border border-emerald-500/40 rounded-lg px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <div className="text-xs text-red-400 mb-1">NO shares</div>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={modalTradeAmountNo}
                    onChange={(e) => setModalTradeAmountNo(Math.max(0, parseInt(e.target.value) || 0))}
                    className="w-28 bg-zinc-900 border border-red-500/40 rounded-lg px-3 py-1.5 text-sm"
                  />
                </div>
                <button
                  onClick={() => onTrade()}
                  disabled={modalTradeAmountYes === 0 && modalTradeAmountNo === 0}
                  className="h-9 px-5 rounded-xl bg-white text-black text-sm font-semibold disabled:bg-zinc-800 disabled:text-zinc-400"
                >
                  Execute Trade
                </button>
                <button onClick={() => { setModalTradeAmountYes(0); setModalTradeAmountNo(0); setModalQuote(null); }} className="h-9 px-4 text-sm border border-zinc-700 rounded-xl">
                  Clear
                </button>
              </div>

              {modalQuote && (
                <div className="text-sm bg-zinc-900 border border-zinc-700 rounded-xl p-3 mb-3">
                  <div>Est. cost: <span className="font-semibold tabular-nums">{modalQuote.effective_cost?.toFixed(2)}</span> (fee {modalQuote.fee?.toFixed(2) || '0.00'})</div>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Price after: {(modalQuote.price_after?.[0]*100||0).toFixed(1)}¢ / {(modalQuote.price_after?.[1]*100||0).toFixed(1)}¢
                    {'  •  '} Impact: {modalQuote.impact?.[0]?.toFixed(4)} / {modalQuote.impact?.[1]?.toFixed(4)}
                    {'  •  '} Slippage: {modalQuote.slippage?.toFixed(4)}
                  </div>
                </div>
              )}

              <div className="text-[10px] text-zinc-400">Positive = buy that side. Negative values allowed for sell. Uses the same integer shares + quote engine as the cards.</div>
            </div>
          ) : (
            <div className="border-t border-zinc-700 pt-4">
              <div className="bg-zinc-900 border border-violet-700/40 rounded-2xl p-4">
                <div className="font-semibold text-violet-300">Market Resolved</div>
                <div className="mt-1">Outcome: <span className="font-bold uppercase tracking-widest">{marketDetail?.resolution_outcome || '—'}</span></div>
                <div className="text-xs text-zinc-400 mt-1">No further trading allowed. Check the price history above and your realized position/payout in the main Portfolio section.</div>
              </div>
            </div>
          )}

          {/* ADMIN VERSION EXTRAS */}
          {activeTab === 'admin' && (
            <div className="border-t border-zinc-700 pt-5 space-y-4">
              <div className="font-semibold text-lg flex items-center gap-2">
                Admin Controls — {marketDetail?.title}
                <span className="text-xs px-2 py-0.5 rounded bg-red-900/30 text-red-300 border border-red-700">ADMIN ONLY</span>
              </div>

              {/* Liquidity */}
              <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-4 text-sm">
                <div className="font-medium mb-1 text-emerald-300">Liquidity Parameter (b)</div>
                <div>Current b: <span className="font-semibold tabular-nums">{(marketDetail?.current_b ?? 0).toFixed(1)}</span></div>
                {marketDetail?.is_adaptive ? (
                  <div className="text-xs text-zinc-400 mt-1">
                    Adaptive strategy
                    {marketDetail?.liquidity_alpha != null && ` • α=${marketDetail.liquidity_alpha.toFixed(4)}`}
                    {marketDetail?.liquidity_min_b != null && ` • min_b=${marketDetail.liquidity_min_b.toFixed(0)}`}
                    {marketDetail?.liquidity_max_b != null && ` • max_b=${marketDetail.liquidity_max_b.toFixed(0)}`}
                  </div>
                ) : (
                  <div className="text-xs text-zinc-400 mt-1">Fixed b (classic LMSR)</div>
                )}
              </div>

              {/* Resolve */}
              <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-4">
                <div className="text-sm font-medium mb-2">Resolve this market</div>
                <div className="flex gap-3 items-center">
                  <select
                    value={resolveOutcome}
                    onChange={e => setResolveOutcome(e.target.value as 'yes'|'no')}
                    className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm"
                  >
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                  <button
                    onClick={async () => {
                      if (!selectedMarketId) return;
                      try {
                        await onResolve(selectedMarketId, resolveOutcome);
                        await onRefresh();
                      } catch (e: any) {
                        // parent handles message
                      }
                    }}
                    className="px-5 h-9 rounded-xl bg-red-600 hover:bg-red-500 text-sm font-semibold"
                  >
                    Resolve Market (Admin)
                  </button>
                </div>
                <div className="text-xs text-zinc-400 mt-1">This affects every user. Payouts and scores are recorded immediately.</div>
              </div>

              {/* Positions */}
              <div>
                <div className="text-sm font-medium mb-2">Current Positions on this market (all users)</div>
                {Object.keys(marketPositions).length === 0 ? (
                  <div className="text-xs text-zinc-400">Loading positions… (or no users)</div>
                ) : (
                  <div className="border border-zinc-800 rounded-xl overflow-hidden text-sm bg-zinc-950">
                    <table className="w-full">
                      <thead className="bg-zinc-900 text-xs text-zinc-400">
                        <tr>
                          <th className="text-left p-2 pl-3">User</th>
                          <th className="text-right p-2">Yes</th>
                          <th className="text-right p-2">No</th>
                          <th className="text-right p-2 pr-3">Net</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {Object.entries(marketPositions).map(([uid, pos]) => (
                          <tr key={uid} className="hover:bg-zinc-900/60">
                            <td className="p-2 pl-3 font-medium">{uid}</td>
                            <td className="p-2 text-right text-emerald-300 tabular-nums">{pos.yes}</td>
                            <td className="p-2 text-right text-red-300 tabular-nums">{pos.no}</td>
                            <td className="p-2 pr-3 text-right text-zinc-400 tabular-nums">{pos.yes - pos.no}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="text-[10px] text-zinc-400 mt-1">Computed live via /observe per user. Updates when you refresh or trade.</div>
              </div>

              <div className="text-xs text-amber-400/80">Tip: Global activity for this market is also visible in the main Admin “Recent Activity” table. You can also change b strategies via the API if needed.</div>

              {/* Resolution PnL */}
              {marketDetail?.status === 'resolved' && marketDetail?.market_maker_pl != null && (
                <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-4">
                  <div className="text-sm font-medium mb-1 text-red-300">Market Maker PnL (this market)</div>
                  <div className="font-semibold tabular-nums text-2xl text-emerald-400">{marketDetail.market_maker_pl.toFixed(2)}</div>
                  <div className="text-[10px] text-zinc-400 mt-1">Revenue collected minus total payouts to winners (subsidy is separate capital at risk).</div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal footer */}
        <div className="border-t border-zinc-800 px-6 py-3 text-xs text-zinc-400 flex justify-between items-center">
          <div>
            This view mirrors the rich per-market experience (price time series + controls) from the Streamlit app.
            {activeTab === 'admin' ? ' Admin extras are only shown in the Admin tab.' : ''}
          </div>
          <button onClick={onClose} className="underline">Close</button>
        </div>
      </div>
    </div>
  );
}
