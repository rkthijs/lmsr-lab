"use client";

import React, { useEffect } from 'react';
import Leaderboard from './components/Leaderboard';
import MarketCard from './components/MarketCard';
import MarketModal from './components/MarketModal';
import { useProData } from './hooks/useProData';

export default function LMSRProfessionalUI() {
  const pro = useProData();

  const {
    selectedUser, setSelectedUser,
    users, markets, activity, account, portfolio, userPositions,
    message, setMessage, activeTab, setActiveTab,
    tradeAmounts,
    resolveMarketId, setResolveMarketId, resolveOutcome, setResolveOutcome,
    scenarios, selectedScenario, setSelectedScenario,
    leaderboard, leaderboardMetric, setLeaderboardMetric,
    selectedMarketId,
    marketDetail, marketTrades, marketPositions,
    hoveredTradeIdx, setHoveredTradeIdx,
    modalTradeAmountYes, setModalTradeAmountYes,
    modalTradeAmountNo, setModalTradeAmountNo,
    modalQuote, setModalQuote,
    getTradeAmount, setTradeAmount,
    refreshAll,
    loadScenarios, loadLeaderboard, loadSelectedScenario, resetSimulator,
    openMarketView, closeMarketView,
    doModalTrade,
    doTrade, doResolve,
    refreshCurrentMarketDetail,
    loadAdminMarketPositions,
    updateModalQuote,
    isLoading, isLoadingAccount, isLoadingPortfolio, isLoadingMarkets,
    isLoadingUsers, isLoadingActivity, isLoadingScenarios, isLoadingLeaderboard,
    isLoadingMarketDetail, isLoadingMarketTrades,
    openMarkets, resolvedMarkets,
  } = pro;

  // Tab switch effect: ensure admin data (scenarios, leaderboard) is fresh when entering Admin view.
  // Core lists / user data / modal details are loaded automatically by TanStack Query (see useProData).
  useEffect(() => {
    if (activeTab === 'admin') {
      loadScenarios();
      loadLeaderboard(leaderboardMetric);
    }
  }, [activeTab, leaderboardMetric]);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="font-semibold tracking-tight text-xl">LMSR Professional</div>
            <div className="text-xs px-2 py-0.5 rounded bg-zinc-900 text-zinc-500">Separate UI</div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div>Backend: <span className="font-mono text-emerald-400">{process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}</span></div>
            <button 
              onClick={refreshAll}
              disabled={isLoading}
              className="px-3 py-1.5 rounded-lg border border-zinc-800 hover:bg-zinc-900 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'Refreshing…' : 'Refresh All'}
            </button>
            <a href="http://localhost:8000/docs" target="_blank" className="text-zinc-500 hover:text-zinc-300">API Docs →</a>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto p-6">
        {/* User Switcher */}
        <div className="mb-6 flex items-center gap-4 bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <div className="font-medium text-sm uppercase tracking-widest text-zinc-500">Viewing as</div>
          <select 
            value={selectedUser} 
            onChange={(e) => setSelectedUser(e.target.value)}
            className="bg-zinc-950 border border-zinc-700 rounded-lg px-4 py-2 text-lg font-semibold focus:outline-none focus:ring-2"
          >
            {users.length > 0 ? (
              users.map(u => (
                <option key={u.user_id} value={u.user_id}>{u.user_id}</option>
              ))
            ) : (
              <option value={selectedUser}>{selectedUser}</option>
            )}
          </select>
          <div className="text-sm text-zinc-500">Switch user to see exactly what they see (portfolios, positions, cash, etc.)</div>
          <div className="ml-auto text-xs px-3 py-1 bg-amber-900/30 text-amber-400 rounded-full">Demo Mode • No real auth</div>
        </div>

        {message && (
          <div
            className={`mb-4 p-3 border rounded-xl text-sm ${
              /error|fail|HTTP \d|insufficient|not found|cannot|invalid|must be|required/i.test(message)
                ? 'bg-red-950 border-red-900 text-red-200'
                : 'bg-blue-950 border-blue-900 text-blue-200'
            }`}
          >
            {message}
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-zinc-800 mb-6">
          <button 
            onClick={() => setActiveTab('user')}
            className={`px-6 py-3 font-medium border-b-2 transition ${activeTab === 'user' ? 'border-white' : 'border-transparent text-zinc-500'}`}
          >
            User View — What {selectedUser} sees
          </button>
          <button 
            onClick={() => setActiveTab('admin')}
            className={`px-6 py-3 font-medium border-b-2 transition ${activeTab === 'admin' ? 'border-white' : 'border-transparent text-zinc-500'}`}
          >
            Admin View — All Activity &amp; Controls
          </button>
        </div>

        {/* USER VIEW */}
        {activeTab === 'user' && (
          <div className="space-y-8">
            {/* Three Values */}
            <div>
              <h2 className="text-xl font-semibold mb-3 tracking-tight">Your Account</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-zinc-900 border border-emerald-500/30 rounded-2xl p-6">
                  <div className="text-xs uppercase tracking-[2px] text-emerald-400">Cash Balance</div>
                  {isLoadingAccount ? (
                    <div className="h-10 w-32 bg-zinc-800 animate-pulse rounded mt-1" />
                  ) : (
                    <div className="text-4xl font-semibold tabular-nums mt-1 text-emerald-400">
                      {account ? account.cash_balance.toFixed(2) : '—'}
                    </div>
                  )}
                </div>
                <div className="bg-zinc-900 border border-blue-500/30 rounded-2xl p-6">
                  <div className="text-xs uppercase tracking-[2px] text-blue-400">Position Value (MTM)</div>
                  {isLoadingAccount ? (
                    <div className="h-10 w-32 bg-zinc-800 animate-pulse rounded mt-1" />
                  ) : (
                    <div className="text-4xl font-semibold tabular-nums mt-1 text-blue-400">
                      {account ? account.position_value.toFixed(2) : '—'}
                    </div>
                  )}
                </div>
                <div className="bg-zinc-900 border border-violet-500/30 rounded-2xl p-6">
                  <div className="text-xs uppercase tracking-[2px] text-violet-400">Total Account Value</div>
                  {isLoadingAccount ? (
                    <div className="h-10 w-32 bg-zinc-800 animate-pulse rounded mt-1" />
                  ) : (
                    <div className="text-4xl font-semibold tabular-nums mt-1 text-violet-400">
                      {account ? account.total_value.toFixed(2) : '—'}
                    </div>
                  )}
                  <div className="text-[10px] text-zinc-500 mt-1">Cash + current market value of your shares</div>
                </div>
              </div>
              <div className="text-[10px] text-zinc-500 mt-2 px-1">
                Note: Buying the "No" side when you hold zero Yes is economically similar to selling Yes (net exposure changes), but they are distinct instruments in the LMSR engine.
              </div>
            </div>

            {/* Portfolio */}
            {(isLoadingPortfolio || portfolio) && (
              <div>
                <h2 className="text-xl font-semibold mb-3">Your Portfolio</h2>
                <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 text-sm">
                  {isLoadingPortfolio ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-3">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <div key={i} className="h-5 bg-zinc-800 animate-pulse rounded" />
                      ))}
                    </div>
                  ) : portfolio ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-3">
                      <div>Open markets: <span className="font-medium">{portfolio.open_markets_count}</span></div>
                      <div>Resolved: <span className="font-medium">{portfolio.resolved_markets_count}</span></div>
                      <div>Realized PnL: <span className="font-medium">{portfolio.realized_pnl.toFixed(2)}</span></div>
                      <div>Total payouts received: <span className="font-medium">{portfolio.total_payouts_received.toFixed(2)}</span></div>
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            {/* Active Markets */}
            <div>
              <h2 className="text-xl font-semibold mb-3">Active Markets</h2>
              <p className="text-sm text-zinc-400 mb-4">
                Click a market card (title or prices) to open the full <strong>Market View</strong> — price history time series (like the Streamlit TRADE tab), recent trades, quote preview, and focused trading.
                Click Buy/Sell for Yes (green) or No (red) on the cards for quick trades. Use "Sell All" to exit cleanly.
                Note: Buying No with zero balance is economically like selling Yes (net exposure), but they are separate instruments.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                {isLoadingMarkets && openMarkets.length === 0 && (
                  Array.from({ length: 2 }).map((_, i) => (
                    <div key={i} className="border border-zinc-800 bg-zinc-900 rounded-2xl p-4 space-y-3">
                      <div className="h-5 w-3/4 bg-zinc-800 animate-pulse rounded" />
                      <div className="flex gap-3">
                        <div className="flex-1 h-8 bg-zinc-800 animate-pulse rounded" />
                        <div className="flex-1 h-8 bg-zinc-800 animate-pulse rounded" />
                      </div>
                      <div className="h-4 w-1/2 bg-zinc-800 animate-pulse rounded" />
                      <div className="flex gap-2">
                        <div className="h-8 w-20 bg-zinc-800 animate-pulse rounded" />
                        <div className="h-8 w-20 bg-zinc-800 animate-pulse rounded" />
                      </div>
                    </div>
                  ))
                )}
                {openMarkets.length === 0 && !isLoadingMarkets && (
                  <div className="text-zinc-400 col-span-full">No active markets. Load a demo scenario (e.g. Full Teaching or 300-round) in the Admin tab.</div>
                )}
                {openMarkets.map(m => {
                  const myPos = userPositions[m.id] || { yes: 0, no: 0 };
                  const amountYes = getTradeAmount(m.id, 'yes');
                  const amountNo = getTradeAmount(m.id, 'no');

                  return (
                    <MarketCard
                      key={m.id}
                      market={m}
                      myPos={myPos}
                      isActive={true}
                      amountYes={amountYes}
                      amountNo={amountNo}
                      onSetAmount={(side, val) => setTradeAmount(m.id, side, val)}
                      onTrade={(yesDelta, noDelta) => doTrade(m.id, yesDelta, noDelta)}
                      onOpenDetail={() => openMarketView(m.id)}
                    />
                  );
                })}
              </div>
            </div>

            {/* Past / Resolved Markets */}
            <div className="mt-10">
              <h2 className="text-xl font-semibold mb-3">Past Markets</h2>
              <p className="text-sm text-zinc-400 mb-4">
                Resolved markets from loaded demo scenarios. Click any card to open the full Market View (price history, trades, your outcome at resolution).
                Your realized PnL and payouts for these are reflected in the Portfolio section above.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                {isLoadingMarkets && resolvedMarkets.length === 0 && (
                  Array.from({ length: 2 }).map((_, i) => (
                    <div key={i} className="border border-zinc-800 bg-zinc-900 rounded-2xl p-4 space-y-3">
                      <div className="h-5 w-3/4 bg-zinc-800 animate-pulse rounded" />
                      <div className="h-4 w-1/2 bg-zinc-800 animate-pulse rounded" />
                      <div className="h-3 w-full bg-zinc-800 animate-pulse rounded" />
                    </div>
                  ))
                )}
                {resolvedMarkets.length === 0 && !isLoadingMarkets && (
                  <div className="text-zinc-400 col-span-full">No resolved markets yet. Load the "Full Teaching Demo (Multi-Market)" in the Admin tab to see examples.</div>
                )}
                {resolvedMarkets.map(m => {
                  const myPos = userPositions[m.id] || { yes: 0, no: 0 };

                  return (
                    <MarketCard
                      key={m.id}
                      market={m}
                      myPos={myPos}
                      isActive={false}
                      amountYes={0}
                      amountNo={0}
                      onSetAmount={() => {}}
                      onTrade={() => {}}
                      onOpenDetail={() => openMarketView(m.id)}
                    />
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ADMIN VIEW */}
        {activeTab === 'admin' && (
          <div className="space-y-8">
            {/* Demo Scenarios */}
            <div>
              <h2 className="text-xl font-semibold mb-3">Demo Scenarios</h2>
              <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
                <div className="flex flex-wrap items-end gap-3">
                  <div className="flex-1 min-w-[280px]">
                    <label className="text-xs block mb-1 text-zinc-500">Curated demo (same as Streamlit Quick Scenarios)</label>
                    <select
                      value={selectedScenario}
                      onChange={e => setSelectedScenario(e.target.value)}
                      className="w-full border border-zinc-700 rounded-lg px-3 py-2 bg-zinc-950"
                    >
                      {scenarios.length === 0 ? (
                        <option value="">No scenarios loaded — see message above or click Reload</option>
                      ) : (
                        scenarios.map(s => (
                          <option key={s} value={s}>{s}</option>
                        ))
                      )}
                    </select>
                  </div>
                  <button
                    onClick={loadSelectedScenario}
                    disabled={!selectedScenario}
                    className="h-10 px-5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium disabled:bg-zinc-800 disabled:text-zinc-500 transition"
                  >
                    Load Selected Scenario
                  </button>
                  <button
                    onClick={resetSimulator}
                    className="h-10 px-5 rounded-xl border border-zinc-700 hover:bg-zinc-800 text-sm font-medium transition"
                  >
                    Reset (empty)
                  </button>
                  <button
                    onClick={loadScenarios}
                    className="h-10 px-3 rounded-xl border border-zinc-700 hover:bg-zinc-800 text-sm font-medium transition"
                    title="Reload scenario list from backend"
                  >
                    ↻ Reload list
                  </button>
                </div>
                <div className="text-[11px] text-zinc-500 mt-2">
                  Loads exactly the same demos as the Streamlit app&apos;s “Quick Demo Scenarios”. Replaces current DB state (markets, users, trades, balances). The 300-round bot demo is pre-selected by default.
                  If the list is empty, make sure you ran the stack from the project root (so the backend can import <code>examples.demo_seeding</code>).
                </div>
              </div>
            </div>

            {/* Quick markets list in admin */}
            <div>
              <h2 className="text-xl font-semibold mb-3">All Markets (click for Admin Market View)</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {isLoadingMarkets && markets.length === 0 && Array.from({ length: 2 }).map((_, i) => (
                  <div key={i} className="border border-zinc-700 bg-zinc-900 rounded-2xl p-3">
                    <div className="h-4 w-2/3 bg-zinc-800 animate-pulse rounded mb-1" />
                    <div className="h-3 w-full bg-zinc-800 animate-pulse rounded" />
                  </div>
                ))}
                {markets.length === 0 && !isLoadingMarkets && <div className="text-sm text-zinc-400">No markets loaded. Load a demo scenario above.</div>}
                {markets.map(m => (
                  <div
                    key={m.id}
                    onClick={() => openMarketView(m.id)}
                    className="cursor-pointer border border-zinc-700 hover:border-red-500/40 bg-zinc-900 rounded-2xl p-3 text-sm flex items-center justify-between"
                  >
                    <div>
                      <div className="font-medium">{m.title}</div>
                      <div className="text-[10px] text-zinc-400">
                        {m.id} • b={m.current_b.toFixed(1)}
                        {m.is_adaptive && m.liquidity_alpha != null && ` (adaptive α=${m.liquidity_alpha.toFixed(3)} min=${(m.liquidity_min_b ?? 0).toFixed(0)})`}
                        • {m.status} • {m.total_trades} trades
                      </div>
                      {m.status === 'resolved' && m.market_maker_pl != null && (
                        <div className="text-[10px] text-emerald-400 mt-0.5">MM PnL: {m.market_maker_pl.toFixed(2)}</div>
                      )}
                    </div>
                    <div className="text-xs text-red-400">Admin detail →</div>
                  </div>
                ))}
              </div>
              <div className="text-[10px] text-zinc-400 mt-1">Opens the admin version of the market view (positions across users, direct resolve, price history, etc.).</div>
            </div>

            <div>
              <h2 className="text-xl font-semibold mb-3">All Users</h2>
              <div className="overflow-auto border border-zinc-800 rounded-2xl">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-900">
                    <tr>
                      <th className="text-left p-4">User</th>
                      <th className="text-right p-4">Balance</th>
                      <th className="text-right p-4">Open Markets</th>
                      <th className="text-right p-4">Resolved</th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLoadingUsers && users.length === 0 && Array.from({ length: 3 }).map((_, i) => (
                      <tr key={i} className="border-t border-zinc-800">
                        <td className="p-4"><div className="h-4 w-16 bg-zinc-800 animate-pulse rounded" /></td>
                        <td className="p-4 text-right"><div className="h-4 w-12 bg-zinc-800 animate-pulse rounded ml-auto" /></td>
                        <td className="p-4 text-right"><div className="h-4 w-8 bg-zinc-800 animate-pulse rounded ml-auto" /></td>
                        <td className="p-4 text-right"><div className="h-4 w-8 bg-zinc-800 animate-pulse rounded ml-auto" /></td>
                      </tr>
                    ))}
                    {users.map(u => (
                      <tr key={u.user_id} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                        <td className="p-4 font-medium">{u.user_id}</td>
                        <td className="p-4 text-right tabular-nums">{u.balance?.toFixed(2)}</td>
                        <td className="p-4 text-right">{u.open_markets ?? '—'}</td>
                        <td className="p-4 text-right">{u.resolved_markets ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Global Leaderboard */}
            <Leaderboard
              leaderboard={leaderboard}
              metric={leaderboardMetric}
              loading={isLoadingLeaderboard}
              onMetricChange={(m) => { setLeaderboardMetric(m); loadLeaderboard(m); }}
            />

            <div>
              <h2 className="text-xl font-semibold mb-3">Recent Activity (All Users)</h2>
              <div className="overflow-auto border border-zinc-800 rounded-2xl max-h-[420px]">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-900 sticky top-0">
                    <tr>
                      <th className="text-left p-3">Time</th>
                      <th className="text-left p-3">User</th>
                      <th className="text-left p-3">Market</th>
                      <th className="text-right p-3">Yes</th>
                      <th className="text-right p-3">No</th>
                      <th className="text-right p-3">Cost</th>
                      <th className="text-right p-3">Fee</th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLoadingActivity && activity.length === 0 && Array.from({ length: 4 }).map((_, i) => (
                      <tr key={i} className="border-t border-zinc-800">
                        {Array.from({ length: 7 }).map((__, j) => (
                          <td key={j} className="p-3"><div className="h-3 bg-zinc-800 animate-pulse rounded" /></td>
                        ))}
                      </tr>
                    ))}
                    {activity.slice(0, 50).map((a, i) => (
                      <tr key={i} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                        <td className="p-3 text-xs text-zinc-500 tabular-nums">{a.timestamp?.slice(11,19) || '—'}</td>
                        <td className="p-3 font-medium">{a.user_id}</td>
                        <td className="p-3 text-xs text-zinc-500">{a.market_title}</td>
                        <td className="p-3 text-right tabular-nums font-mono">{a.shares_yes}</td>
                        <td className="p-3 text-right tabular-nums font-mono">{a.shares_no}</td>
                        <td className="p-3 text-right tabular-nums">{a.effective_cost.toFixed(2)}</td>
                        <td className="p-3 text-right tabular-nums text-emerald-400">{a.fee.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="text-xs text-zinc-500 mt-1">Showing most recent activity across all users and markets.</div>
            </div>

            <div>
              <h2 className="text-xl font-semibold mb-3">Resolve Markets (Admin)</h2>
              <div className="flex gap-3 items-end bg-zinc-900 border border-zinc-800 p-4 rounded-2xl">
                <div className="flex-1">
                  <label className="text-xs block mb-1 text-zinc-500">Market ID</label>
                  <input 
                    value={resolveMarketId} 
                    onChange={e => setResolveMarketId(e.target.value)} 
                    placeholder="e.g. m1" 
                    className="w-full border border-zinc-700 rounded-lg px-3 py-2 bg-zinc-950" 
                  />
                </div>
                <div>
                  <label className="text-xs block mb-1 text-zinc-500">Outcome</label>
                  <select value={resolveOutcome} onChange={e => setResolveOutcome(e.target.value as 'yes'|'no')} className="border border-zinc-700 rounded-lg px-3 py-2 bg-zinc-950">
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
                <button 
                  onClick={doResolve}
                  className="h-10 px-6 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 active:bg-red-800"
                >
                  Resolve Market
                </button>
              </div>
              <div className="text-xs text-zinc-500 mt-2">This resolves the market for everyone. Payouts are credited immediately.</div>
            </div>
          </div>
        )}

        {/* Market Detail Modal - extracted */}
        <MarketModal
          selectedMarketId={selectedMarketId}
          marketDetail={marketDetail}
          marketTrades={marketTrades}
          marketPositions={marketPositions}
          hoveredTradeIdx={hoveredTradeIdx}
          setHoveredTradeIdx={setHoveredTradeIdx}
          modalTradeAmountYes={modalTradeAmountYes}
          setModalTradeAmountYes={setModalTradeAmountYes}
          modalTradeAmountNo={modalTradeAmountNo}
          setModalTradeAmountNo={setModalTradeAmountNo}
          modalQuote={modalQuote}
          setModalQuote={setModalQuote}
          activeTab={activeTab}
          selectedUser={selectedUser}
          resolveOutcome={resolveOutcome}
          setResolveOutcome={setResolveOutcome}
          onClose={closeMarketView}
          onTrade={() => doModalTrade()}
          onRefresh={refreshCurrentMarketDetail}
          onResolve={async (mid, outcome) => {
            setResolveMarketId(mid);
            setResolveOutcome(outcome);
            await doResolve();
            setMessage(`Resolved ${mid} to ${outcome} (admin).`);
            await refreshCurrentMarketDetail();
            await refreshAll();
          }}
          onLoadAdminPositions={loadAdminMarketPositions}
          onUpdateQuote={updateModalQuote}
          isLoadingMarketDetail={isLoadingMarketDetail}
          isLoadingMarketTrades={isLoadingMarketTrades}
          isLoadingPositions={activeTab === 'admin' && !!selectedMarketId}
        />

        <div className="mt-12 text-xs text-zinc-500 border-t pt-6">
          Professional separate frontend (Next.js) • Backend: FastAPI on {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'} • 
          Make sure the backend is running (<code>lmsr serve</code> or <code>uvicorn lmsr.api:app --port 8000</code>) and has data (run the 300-round script or a demo scenario).
        </div>
      </div>
    </div>
  );
}
