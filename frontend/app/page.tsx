"use client";

import React, { useState, useEffect } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface User {
  user_id: string;
  balance: number;
  open_markets?: number;
  resolved_markets?: number;
}

interface Market {
  id: string;
  title: string;
  status: string;
  current_prices: [number, number];
  current_b: number;
  is_adaptive: boolean;
  total_trades: number;
  total_fees_earned: number;
  resolution_outcome?: string | null;
  market_maker_pl?: number | null;
  is_adaptive?: boolean;
  liquidity_alpha?: number | null;
  liquidity_min_b?: number | null;
  liquidity_max_b?: number | null;
}

interface ActivityItem {
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

interface Account {
  user_id: string;
  cash_balance: number;
  position_value: number;
  total_value: number;
}

interface Portfolio {
  user_id: string;
  balance: number;
  positions: Record<string, { yes: number; no: number; total: number; value?: number }>;
  realized_pnl: number;
  total_payouts_received: number;
  open_markets_count: number;
  resolved_markets_count: number;
}

export default function LMSRProfessionalUI() {
  const [selectedUser, setSelectedUser] = useState<string>('bull');
  const [users, setUsers] = useState<User[]>([]);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [account, setAccount] = useState<Account | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [userPositions, setUserPositions] = useState<Record<string, { yes: number; no: number }>>({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState<'user' | 'admin'>('user');

  // Per-market trade amounts (positive number means "how many to buy/sell" for that side)
  const [tradeAmounts, setTradeAmounts] = useState<Record<string, { yes: number; no: number }>>({});

  // Resolve form
  const [resolveMarketId, setResolveMarketId] = useState('');
  const [resolveOutcome, setResolveOutcome] = useState<'yes' | 'no'>('yes');

  // Demo scenarios (populated from backend; same SCENARIO_REGISTRY as the Streamlit app)
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>('');

  // Market detail view (clicking a market opens this; similar to Streamlit TRADE/MARKET VIEW + time series)
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [marketDetail, setMarketDetail] = useState<any>(null);
  const [marketTrades, setMarketTrades] = useState<any[]>([]);
  const [marketPositions, setMarketPositions] = useState<Record<string, { yes: number; no: number }>>({});
  const [hoveredTradeIdx, setHoveredTradeIdx] = useState<number | null>(null);
  const [modalTradeAmountYes, setModalTradeAmountYes] = useState(0);
  const [modalTradeAmountNo, setModalTradeAmountNo] = useState(0);
  const [modalQuote, setModalQuote] = useState<any>(null);

  async function fetchJson(url: string, options?: RequestInit) {
    const fullUrl = `${API_BASE}${url}`;
    const res = await fetch(fullUrl, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
    });
    if (!res.ok) {
      let message = `HTTP ${res.status} ${res.statusText || ''}`.trim();
      try {
        const body = await res.json();
        if (body) {
          if (typeof body.detail === 'string') {
            message = body.detail;
          } else if (Array.isArray(body.detail)) {
            // FastAPI/Pydantic validation errors (422) — common for bad inputs
            message = body.detail
              .map((d: any) =>
                typeof d === 'string'
                  ? d
                  : (d?.msg || d?.message || (d?.loc ? JSON.stringify(d) : ''))
              )
              .filter(Boolean)
              .join('; ') || message;
          } else if (body.error) {
            message = typeof body.error === 'string' ? body.error : JSON.stringify(body.error);
          } else if (body.message) {
            message = body.message;
          } else if (typeof body === 'object') {
            message = JSON.stringify(body);
          }
        }
      } catch {
        // Body was not JSON — try to read as text (e.g. 500 HTML or plain text)
        try {
          const text = await res.text();
          if (text) message = text.slice(0, 300); // cap huge error pages
        } catch {
          /* ignore */
        }
      }
      const err = new Error(`${message} (url: ${url})`);
      // Attach extra info for debugging in console
      (err as any).status = res.status;
      (err as any).url = fullUrl;
      throw err;
    }
    return res.json();
  }

  async function loadUsers() {
    try {
      const data: User[] = await fetchJson('/admin/users');
      setUsers(data);
      if (data.length > 0) {
        const preferred = ['bull', 'contrarian', 'trend', 'random'];
        const foundPreferred = preferred.find(p => data.some(u => u.user_id === p));
        if (foundPreferred && !data.find(u => u.user_id === selectedUser)) {
          setSelectedUser(foundPreferred);
        } else if (!data.find(u => u.user_id === selectedUser)) {
          setSelectedUser(data[0].user_id);
        }
      }
    } catch (e: any) {
      setMessage('Failed to load users: ' + e.message + '. Is the backend running on :8000?');
    }
  }

  async function loadMarkets() {
    try {
      const data: Market[] = await fetchJson('/admin/markets');
      setMarkets(data);
    } catch (e: any) {
      console.error(e);
    }
  }

  async function loadActivity() {
    try {
      const data: ActivityItem[] = await fetchJson('/admin/activity?limit=100');
      setActivity(data);
    } catch (e: any) {
      console.error(e);
    }
  }

  async function loadUserData(userId: string) {
    setLoading(true);
    setMessage('');
    try {
      const [acc, port] = await Promise.all([
        fetchJson(`/users/${userId}/account`),
        fetchJson(`/users/${userId}/portfolio`),
      ]);
      setAccount(acc);
      setPortfolio(port);

      // Load per-market positions for open markets using observe
      const posMap: Record<string, { yes: number; no: number }> = {};
      for (const m of markets) {
        try {
          const obs = await fetchJson(`/markets/${m.id}/observe?user_id=${userId}`);
          posMap[m.id] = obs.position;
        } catch {}
      }
      setUserPositions(posMap);
    } catch (e: any) {
      setMessage('Failed to load user data: ' + e.message);
    } finally {
      setLoading(false);
    }
  }

  async function refreshAll() {
    await Promise.all([loadUsers(), loadMarkets(), loadActivity()]);
    if (selectedUser) await loadUserData(selectedUser);
  }

  // Scenario helpers (declared early so they are in scope for useEffects and refresh)
  async function loadScenarios() {
    try {
      const data = await fetchJson('/admin/scenarios');
      const list: string[] = data.scenarios || [];
      setScenarios(list);
      if (list.length > 0 && !selectedScenario) {
        // Prefer the rich 300-round bot demo if present (default for this UI)
        const preferred = list.find(s => s.includes('300') || s.includes('Bot')) || list[0];
        setSelectedScenario(preferred);
      }
      if (data.error) {
        setMessage('Scenarios failed to load: ' + data.error);
      }
    } catch (e: any) {
      setScenarios([]);
      setMessage('Failed to load scenario list (check backend logs / is examples/ importable?): ' + e.message);
    }
  }

  async function loadSelectedScenario() {
    if (!selectedScenario) return;
    setMessage('Loading demo scenario...');
    try {
      const res = await fetchJson('/admin/scenarios/load', {
        method: 'POST',
        body: JSON.stringify({ name: selectedScenario }),
      });
      setMessage(res.message || `Loaded scenario: ${selectedScenario}`);
      // Refresh everything; loadUsers will auto-pick a reasonable user from the new set
      closeMarketView(); // new scenario may have completely different markets
      await refreshAll();
    } catch (e: any) {
      setMessage('Load scenario failed: ' + e.message);
    }
  }

  async function resetSimulator() {
    setMessage('Resetting simulator...');
    try {
      await fetchJson('/reset', { method: 'POST' });
      setMessage('Simulator reset to empty state.');
      await refreshAll();
    } catch (e: any) {
      setMessage('Reset failed: ' + e.message);
    }
  }

  // --- Market Detail View helpers (time series + admin version) ---
  async function loadMarketTrades(marketId: string) {
    try {
      const trades = await fetchJson(`/markets/${marketId}/trades`);
      setMarketTrades(Array.isArray(trades) ? trades : []);
    } catch (e: any) {
      setMarketTrades([]);
    }
  }

  async function loadMarketDetail(marketId: string) {
    try {
      // Use the dedicated admin endpoint when in Admin tab for extra fields
      // like market_maker_pl and full liquidity strategy details.
      const path = activeTab === 'admin' ? `/admin/markets/${marketId}` : `/markets/${marketId}`;
      const m = await fetchJson(path);
      setMarketDetail(m);
    } catch (e: any) {
      setMarketDetail(null);
    }
  }

  async function loadAdminMarketPositions(marketId: string) {
    // Only meaningful in admin; uses current users list + observe per user
    if (users.length === 0) return;
    const posMap: Record<string, { yes: number; no: number }> = {};
    await Promise.all(users.map(async (u) => {
      try {
        const obs = await fetchJson(`/markets/${marketId}/observe?user_id=${u.user_id}`);
        posMap[u.user_id] = obs.position || { yes: 0, no: 0 };
      } catch {
        posMap[u.user_id] = { yes: 0, no: 0 };
      }
    }));
    setMarketPositions(posMap);
  }

  async function openMarketView(marketId: string) {
    setSelectedMarketId(marketId);
    setHoveredTradeIdx(null);
    setModalTradeAmountYes(0);
    setModalTradeAmountNo(0);
    setModalQuote(null);
    setMarketPositions({});

    await Promise.all([
      loadMarketDetail(marketId),
      loadMarketTrades(marketId),
    ]);

    if (activeTab === 'admin') {
      await loadAdminMarketPositions(marketId);
    }
  }

  function closeMarketView() {
    setSelectedMarketId(null);
    setMarketDetail(null);
    setMarketTrades([]);
    setMarketPositions({});
    setHoveredTradeIdx(null);
    setModalTradeAmountYes(0);
    setModalTradeAmountNo(0);
    setModalQuote(null);
  }

  async function refreshCurrentMarketDetail() {
    if (!selectedMarketId) return;
    await Promise.all([
      loadMarketDetail(selectedMarketId),
      loadMarketTrades(selectedMarketId),
    ]);
    if (activeTab === 'admin') {
      await loadAdminMarketPositions(selectedMarketId);
    }
  }

  // Live quote inside modal (for the focused market + current selectedUser)
  async function updateModalQuote(yesDelta: number, noDelta: number) {
    if (!selectedMarketId) return;
    if (yesDelta === 0 && noDelta === 0) {
      setModalQuote(null);
      return;
    }
    try {
      const q = await fetchJson(
        `/markets/${selectedMarketId}/quote?shares_yes=${yesDelta}&shares_no=${noDelta}`
      );
      setModalQuote(q);
    } catch {
      setModalQuote(null);
    }
  }

  // Execute trade from inside the modal (re-uses global doTrade then refreshes the detail)
  async function doModalTrade() {
    if (!selectedMarketId) return;
    const y = modalTradeAmountYes;
    const n = modalTradeAmountNo;
    if (y === 0 && n === 0) return;
    try {
      await doTrade(selectedMarketId, y, n);  // existing global handler (shows message + refreshAll)
      // Clear local amounts + requote + reload series for this market
      setModalTradeAmountYes(0);
      setModalTradeAmountNo(0);
      setModalQuote(null);
      await refreshCurrentMarketDetail();
    } catch (e: any) {
      setMessage('Modal trade error: ' + e.message);
    }
  }

  useEffect(() => {
    // Dark mode is enforced at the layout level (html.dark + body zinc-950)
    refreshAll();
    loadScenarios();
  }, []);

  useEffect(() => {
    if (selectedUser) {
      loadUserData(selectedUser);
    }
  }, [selectedUser, markets]);

  // Reload scenarios when switching to the Admin tab (so the dropdown can recover
  // if the first fetch happened before the server was fully ready or examples import failed temporarily).
  useEffect(() => {
    if (activeTab === 'admin') {
      loadScenarios();
    }
  }, [activeTab]);

  // Keyboard support for modal: Esc closes market detail view
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && selectedMarketId) {
        closeMarketView();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedMarketId]);

  // Live quote when modal trade amounts change
  useEffect(() => {
    if (selectedMarketId) {
      updateModalQuote(modalTradeAmountYes, modalTradeAmountNo);
    }
  }, [modalTradeAmountYes, modalTradeAmountNo, selectedMarketId]);

  // Unified trade: positive amount = buy that side, negative = sell that side
  async function doTrade(marketId: string, yesDelta: number, noDelta: number) {
    if (yesDelta === 0 && noDelta === 0) return;
    setMessage('');
    try {
      const res = await fetchJson(`/markets/${marketId}/trades`, {
        method: 'POST',
        body: JSON.stringify({
          user_id: selectedUser,
          shares_yes: yesDelta,
          shares_no: noDelta,
        }),
      });
      if (res.error) {
        setMessage(`Trade failed: ${res.error}`);
      } else {
        setMessage(`Trade executed. Cost: ${res.cost?.toFixed(2)} (fee ${res.fee?.toFixed(2) || '0.00'})`);
        // Clear the amount for that market
        setTradeAmounts(prev => ({ ...prev, [marketId]: { yes: 0, no: 0 } }));
        await refreshAll();
        if (selectedMarketId === marketId) {
          await refreshCurrentMarketDetail();
        }
      }
    } catch (e: any) {
      setMessage('Trade error: ' + e.message);
    }
  }

  const getTradeAmount = (marketId: string, side: 'yes' | 'no') => {
    return tradeAmounts[marketId]?.[side] || 0;
  };

  const setTradeAmount = (marketId: string, side: 'yes' | 'no', val: number) => {
    setTradeAmounts(prev => ({
      ...prev,
      [marketId]: {
        ...(prev[marketId] || { yes: 0, no: 0 }),
        [side]: val
      }
    }));
  };

  async function doResolve() {
    if (!resolveMarketId) return;
    setMessage('');
    try {
      const res = await fetchJson(`/admin/markets/${resolveMarketId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ outcome: resolveOutcome }),
      });
      setMessage(`Market ${resolveMarketId} resolved to ${resolveOutcome}.`);
      await refreshAll();
      if (selectedMarketId === resolveMarketId) {
        await refreshCurrentMarketDetail();
      }
    } catch (e: any) {
      setMessage('Resolve error: ' + e.message);
    }
  }

  const openMarkets = markets.filter(m => m.status === 'open');
  const resolvedMarkets = markets.filter(m => m.status === 'resolved');

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="font-semibold tracking-tight text-xl">LMSR Professional</div>
            <div className="text-xs px-2 py-0.5 rounded bg-zinc-900 text-zinc-500">Separate UI</div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div>Backend: <span className="font-mono text-emerald-400">{API_BASE}</span></div>
            <button 
              onClick={refreshAll}
              className="px-3 py-1.5 rounded-lg border border-zinc-800 hover:bg-zinc-900 transition"
            >
              Refresh All
            </button>
            <a href="http://localhost:8000/docs" target="_blank" className="text-zinc-500 hover:text-zinc-300">API Docs →</a>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto p-6">
        {/* User Switcher - "see what each user sees" */}
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
            {/* Three Values - always visible, Kalshi-inspired dark cards */}
            <div>
              <h2 className="text-xl font-semibold mb-3 tracking-tight">Your Account</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-zinc-900 border border-emerald-500/30 rounded-2xl p-6">
                  <div className="text-xs uppercase tracking-[2px] text-emerald-400">Cash Balance</div>
                  <div className="text-4xl font-semibold tabular-nums mt-1 text-emerald-400">
                    {account ? account.cash_balance.toFixed(2) : '—'}
                  </div>
                </div>
                <div className="bg-zinc-900 border border-blue-500/30 rounded-2xl p-6">
                  <div className="text-xs uppercase tracking-[2px] text-blue-400">Position Value (MTM)</div>
                  <div className="text-4xl font-semibold tabular-nums mt-1 text-blue-400">
                    {account ? account.position_value.toFixed(2) : '—'}
                  </div>
                </div>
                <div className="bg-zinc-900 border border-violet-500/30 rounded-2xl p-6">
                  <div className="text-xs uppercase tracking-[2px] text-violet-400">Total Account Value</div>
                  <div className="text-4xl font-semibold tabular-nums mt-1 text-violet-400">
                    {account ? account.total_value.toFixed(2) : '—'}
                  </div>
                  <div className="text-[10px] text-zinc-500 mt-1">Cash + current market value of your shares</div>
                </div>
              </div>
              <div className="text-[10px] text-zinc-500 mt-2 px-1">
                Note: Buying the "No" side when you hold zero Yes is economically similar to selling Yes (net exposure changes), but they are distinct instruments in the LMSR engine.
              </div>
            </div>

            {/* Portfolio */}
            {portfolio && (
              <div>
                <h2 className="text-xl font-semibold mb-3">Your Portfolio</h2>
                <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 text-sm">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-3">
                    <div>Open markets: <span className="font-medium">{portfolio.open_markets_count}</span></div>
                    <div>Resolved: <span className="font-medium">{portfolio.resolved_markets_count}</span></div>
                    <div>Realized PnL: <span className="font-medium">{portfolio.realized_pnl.toFixed(2)}</span></div>
                    <div>Total payouts received: <span className="font-medium">{portfolio.total_payouts_received.toFixed(2)}</span></div>
                  </div>
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
                {openMarkets.length === 0 && (
                  <div className="text-zinc-400 col-span-full">No active markets. Load a demo scenario (e.g. Full Teaching or 300-round) in the Admin tab.</div>
                )}
                {openMarkets.map(m => {
                  const myPos = userPositions[m.id] || { yes: 0, no: 0 };
                  const amountYes = getTradeAmount(m.id, 'yes');
                  const amountNo = getTradeAmount(m.id, 'no');

                  const yesPrice = m.current_prices[0];
                  const noPrice = m.current_prices[1];

                  return (
                    <div
                      key={m.id}
                      onClick={() => openMarketView(m.id)}
                      className="border border-zinc-700 rounded-2xl bg-zinc-900 p-5 text-white cursor-pointer hover:border-emerald-500/40 hover:bg-zinc-950 transition"
                      title="Click for full market view (price history time series, details, admin tools)"
                    >
                      <div className="font-semibold text-lg mb-1 flex items-center justify-between">
                        {m.title}
                        <span className="text-[10px] text-emerald-400/70 font-normal">View details →</span>
                      </div>
                      <div className="text-xs text-zinc-400 mb-3">{m.id} • b={m.current_b.toFixed(1)} • {m.status}</div>

                      {/* Prices - Kalshi style big colored % : Yes = green (emerald), No = red */}
                      <div className="flex gap-3 mb-4">
                        <div className="flex-1 bg-zinc-950 border border-emerald-500/40 rounded-xl p-3 text-center">
                          <div className="text-xs text-emerald-400 font-medium tracking-wider">YES</div>
                          <div className="text-4xl font-bold text-emerald-400 tabular-nums">{(yesPrice * 100).toFixed(1)}<span className="text-xl align-super">¢</span></div>
                          <div className="text-[10px] text-zinc-500">Current Price</div>
                        </div>
                        <div className="flex-1 bg-zinc-950 border border-red-500/40 rounded-xl p-3 text-center">
                          <div className="text-xs text-red-400 font-medium tracking-wider">NO</div>
                          <div className="text-4xl font-bold text-red-400 tabular-nums">{(noPrice * 100).toFixed(1)}<span className="text-xl align-super">¢</span></div>
                          <div className="text-[10px] text-zinc-500">Current Price</div>
                        </div>
                      </div>

                      {/* Your Position */}
                      <div className="mb-4 text-sm">
                        <div className="text-xs text-zinc-400 mb-1">YOUR POSITION</div>
                        <div className="flex gap-4">
                          <div>Yes: <span className="font-semibold text-emerald-400">{myPos.yes}</span></div>
                          <div>No: <span className="font-semibold text-red-400">{myPos.no}</span></div>
                          <div className="text-zinc-400 text-xs self-center">Net: {myPos.yes - myPos.no}</div>
                        </div>
                      </div>

                      {/* Sell All - important for exiting cleanly */}
                      <div className="flex gap-2 mb-4">
                        {myPos.yes > 0 && (
                          <button
                            onClick={(e) => { e.stopPropagation(); doTrade(m.id, -myPos.yes, 0); }}
                            className="flex-1 text-sm py-1.5 rounded-lg border border-emerald-400 text-emerald-200 hover:bg-emerald-900/40 active:bg-emerald-900/60 transition"
                          >
                            Sell All Yes ({myPos.yes})
                          </button>
                        )}
                        {myPos.no > 0 && (
                          <button
                            onClick={(e) => { e.stopPropagation(); doTrade(m.id, 0, -myPos.no); }}
                            className="flex-1 text-sm py-1.5 rounded-lg border border-red-400 text-red-200 hover:bg-red-900/40 active:bg-red-900/60 transition"
                          >
                            Sell All No ({myPos.no})
                          </button>
                        )}
                      </div>

                      {/* Trade controls - click buy/sell then enter amount */}
                      <div className="space-y-3 border-t border-zinc-700 pt-4">
                        {/* Yes side - green */}
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-emerald-400 font-semibold text-sm tracking-wider">YES</span>
                          </div>
                          <div className="flex gap-2">
                            <input
                              type="number"
                              min="0"
                              step="1"
                              value={amountYes}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => { e.stopPropagation(); setTradeAmount(m.id, 'yes', Math.max(0, parseInt(e.target.value) || 0)); }}
                              className="w-24 bg-zinc-950 border border-emerald-500/40 rounded-lg px-3 py-1.5 text-sm text-emerald-100 focus:outline-none focus:border-emerald-400"
                              placeholder="shares"
                            />
                            <button
                              onClick={(e) => { e.stopPropagation(); doTrade(m.id, amountYes, 0); }}
                              disabled={amountYes === 0}
                              className="flex-1 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 disabled:bg-zinc-800 disabled:text-zinc-500 text-white font-semibold text-sm rounded-lg py-1.5 transition"
                            >
                              Buy Yes
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); doTrade(m.id, -amountYes, 0); }}
                              disabled={amountYes === 0}
                              className="flex-1 bg-emerald-950 hover:bg-emerald-900 border border-emerald-400 text-emerald-200 font-semibold text-sm rounded-lg py-1.5 transition disabled:opacity-50"
                            >
                              Sell Yes
                            </button>
                          </div>
                        </div>

                        {/* No side - red */}
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-red-400 font-semibold text-sm tracking-wider">NO</span>
                          </div>
                          <div className="flex gap-2">
                            <input
                              type="number"
                              min="0"
                              step="1"
                              value={amountNo}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => { e.stopPropagation(); setTradeAmount(m.id, 'no', Math.max(0, parseInt(e.target.value) || 0)); }}
                              className="w-24 bg-zinc-950 border border-red-500/40 rounded-lg px-3 py-1.5 text-sm text-red-100 focus:outline-none focus:border-red-400"
                              placeholder="shares"
                            />
                            <button
                              onClick={(e) => { e.stopPropagation(); doTrade(m.id, 0, amountNo); }}
                              disabled={amountNo === 0}
                              className="flex-1 bg-red-600 hover:bg-red-500 active:bg-red-700 disabled:bg-zinc-800 disabled:text-zinc-500 text-white font-semibold text-sm rounded-lg py-1.5 transition"
                            >
                              Buy No
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); doTrade(m.id, 0, -amountNo); }}
                              disabled={amountNo === 0}
                              className="flex-1 bg-red-950 hover:bg-red-900 border border-red-400 text-red-200 font-semibold text-sm rounded-lg py-1.5 transition disabled:opacity-50"
                            >
                              Sell No
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Past / Resolved Markets - now visible to users under their own heading */}
            <div className="mt-10">
              <h2 className="text-xl font-semibold mb-3">Past Markets</h2>
              <p className="text-sm text-zinc-400 mb-4">
                Resolved markets from loaded demo scenarios. Click any card to open the full Market View (price history, trades, your outcome at resolution).
                Your realized PnL and payouts for these are reflected in the Portfolio section above.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                {resolvedMarkets.length === 0 && (
                  <div className="text-zinc-400 col-span-full">No resolved markets yet. Load the "Full Teaching Demo (Multi-Market)" in the Admin tab to see examples.</div>
                )}
                {resolvedMarkets.map(m => {
                  const myPos = userPositions[m.id] || { yes: 0, no: 0 };
                  const yesPrice = m.current_prices[0];
                  const noPrice = m.current_prices[1];

                  return (
                    <div
                      key={m.id}
                      onClick={() => openMarketView(m.id)}
                      className="border border-zinc-700 rounded-2xl bg-zinc-900 p-5 text-white cursor-pointer hover:border-violet-500/40 hover:bg-zinc-950 transition opacity-90"
                      title="Click for full history, price path at resolution, and outcome details"
                    >
                      <div className="font-semibold text-lg mb-1 flex items-center justify-between">
                        {m.title}
                        <span className="text-[10px] px-2 py-0.5 rounded bg-violet-900/40 text-violet-300 text-xs">RESOLVED</span>
                      </div>
                      <div className="text-xs text-zinc-400 mb-3">{m.id} • b={m.current_b.toFixed(1)} • resolved to {m.resolution_outcome?.toUpperCase() || '—'}</div>

                      {/* Final Prices */}
                      <div className="flex gap-3 mb-4">
                        <div className="flex-1 bg-zinc-950 border border-emerald-500/40 rounded-xl p-3 text-center">
                          <div className="text-xs text-emerald-400 font-medium tracking-wider">YES (final)</div>
                          <div className="text-4xl font-bold text-emerald-400 tabular-nums">{(yesPrice * 100).toFixed(1)}<span className="text-xl align-super">¢</span></div>
                        </div>
                        <div className="flex-1 bg-zinc-950 border border-red-500/40 rounded-xl p-3 text-center">
                          <div className="text-xs text-red-400 font-medium tracking-wider">NO (final)</div>
                          <div className="text-4xl font-bold text-red-400 tabular-nums">{(noPrice * 100).toFixed(1)}<span className="text-xl align-super">¢</span></div>
                        </div>
                      </div>

                      {/* Your Position at resolution */}
                      <div className="mb-3 text-sm">
                        <div className="text-xs text-zinc-400 mb-1">YOUR POSITION (at resolution)</div>
                        <div className="flex gap-4">
                          <div>Yes: <span className="font-semibold text-emerald-400">{myPos.yes}</span></div>
                          <div>No: <span className="font-semibold text-red-400">{myPos.no}</span></div>
                          <div className="text-zinc-400 text-xs self-center">Net: {myPos.yes - myPos.no}</div>
                        </div>
                      </div>

                      <div className="text-[10px] text-violet-400/70 mt-2">View full price path and outcome details →</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* ADMIN VIEW */}
        {activeTab === 'admin' && (
          <div className="space-y-8">
            {/* Demo Scenarios - now all Streamlit demos are available here too */}
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

            {/* Quick markets list in admin so you can directly open the admin market view */}
            <div>
              <h2 className="text-xl font-semibold mb-3">All Markets (click for Admin Market View)</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {markets.length === 0 && <div className="text-sm text-zinc-400">No markets loaded. Load a demo scenario above.</div>}
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

        {/* ==================== MARKET DETAIL MODAL (User + Admin versions) ==================== */}
        {selectedMarketId && (
          <div
            className="fixed inset-0 z-[100] flex items-start justify-center bg-black/70 p-4 pt-12 overflow-y-auto"
            onClick={closeMarketView}
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
                    onClick={closeMarketView}
                    className="px-4 py-2 text-sm rounded-xl border border-zinc-700 hover:bg-zinc-900 transition"
                  >
                    Close (Esc)
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-6">
                {/* Big current prices (Kalshi style, consistent with list) */}
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

                {/* TIME SERIES: Price History (the main thing the user asked for, matching Streamlit) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-semibold text-lg">Price History — P(Yes)</div>
                    <div className="text-xs text-zinc-400">Y-axis fixed 0 → 1.0 (like Streamlit TRADE tab)</div>
                  </div>

                  {/* Interactive SVG Price Chart - pure, no extra deps */}
                  {(() => {
                    const series = [0.5];
                    marketTrades.forEach((t: any) => {
                      if (typeof t.price_after_yes === 'number') series.push(t.price_after_yes);
                    });
                    const n = series.length;
                    if (n < 2) {
                      return <div className="text-sm text-zinc-400 bg-zinc-900 border border-zinc-800 rounded-2xl p-6">No trades yet — the market starts at 50/50. Make the first trade to see the time series.</div>;
                    }

                    const W = 820;
                    const H = 240;
                    const PAD = 36;
                    const CHART_W = W - PAD * 2;
                    const CHART_H = H - PAD * 2;

                    const points = series.map((p, i) => {
                      const x = PAD + (n > 1 ? (i / (n - 1)) * CHART_W : 0);
                      const y = PAD + (1 - Math.max(0, Math.min(1, p))) * CHART_H;
                      return { x, y, p, i };
                    });

                    const pathD = points.map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');

                    const onMove = (evt: React.MouseEvent<SVGSVGElement>) => {
                      const rect = (evt.currentTarget as any).getBoundingClientRect();
                      const mx = ((evt.clientX - rect.left) / rect.width) * W;
                      let best = 0;
                      let bestDist = Infinity;
                      points.forEach((pt, idx) => {
                        const d = Math.abs(pt.x - mx);
                        if (d < bestDist) { bestDist = d; best = idx; }
                      });
                      setHoveredTradeIdx(best);
                    };

                    const onLeave = () => setHoveredTradeIdx(null);

                    const hovered = hoveredTradeIdx != null ? points[hoveredTradeIdx] : null;

                    return (
                      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-4 relative">
                        <svg
                          width="100%"
                          height={H}
                          viewBox={`0 0 ${W} ${H}`}
                          className="overflow-visible"
                          onMouseMove={onMove}
                          onMouseLeave={onLeave}
                        >
                          {/* Grid + Y labels (fixed 0-1) */}
                          {[0, 0.25, 0.5, 0.75, 1].map((v, i) => {
                            const y = PAD + (1 - v) * CHART_H;
                            return (
                              <g key={i}>
                                <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="#3f3f46" strokeWidth="1" />
                                <text x={PAD - 6} y={y + 4} fill="#71717a" fontSize="11" textAnchor="end">{v.toFixed(1)}</text>
                              </g>
                            );
                          })}

                          {/* X axis label */}
                          <text x={W / 2} y={H - 6} fill="#71717a" fontSize="11" textAnchor="middle">Trade # (sequence of executed trades)</text>

                          {/* The price path line */}
                          <path d={pathD} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />

                          {/* Dots + hover highlight */}
                          {points.map((pt, idx) => (
                            <circle
                              key={idx}
                              cx={pt.x}
                              cy={pt.y}
                              r={hoveredTradeIdx === idx ? 5 : 2.5}
                              fill={hoveredTradeIdx === idx ? "#10b981" : "#10b981"}
                              stroke={hoveredTradeIdx === idx ? "#fff" : "none"}
                              strokeWidth={hoveredTradeIdx === idx ? 1.5 : 0}
                            />
                          ))}

                          {/* Hover vertical guide + tooltip anchor */}
                          {hovered && (
                            <line
                              x1={hovered.x}
                              y1={PAD}
                              x2={hovered.x}
                              y2={H - PAD}
                              stroke="#10b981"
                              strokeWidth="1"
                              strokeDasharray="3 2"
                              opacity="0.6"
                            />
                          )}
                        </svg>

                        {/* Tooltip */}
                        {hovered && (
                          <div
                            className="absolute bg-zinc-800 border border-emerald-500/50 text-xs px-3 py-1 rounded shadow pointer-events-none"
                            style={{
                              left: `${((hovered.x / W) * 100).toFixed(1)}%`,
                              top: 12,
                              transform: 'translate(-50%, 0)'
                            }}
                          >
                            Trade #{hovered.i} • P(Yes) = <span className="font-semibold text-emerald-400">{(hovered.p * 100).toFixed(1)}¢</span>
                          </div>
                        )}

                        <div className="text-[10px] text-zinc-400 mt-1">
                          {series.length - 1} trades • Drag mouse over the chart for exact values. Starts at 0.50 before any trading.
                        </div>
                      </div>
                    );
                  })()}
                </div>

                {/* Recent trades table (from /trades API) */}
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

                {/* Focused trading + quote inside the market view (only for open markets) */}
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
                        onClick={doModalTrade}
                        disabled={modalTradeAmountYes === 0 && modalTradeAmountNo === 0}
                        className="h-9 px-5 rounded-xl bg-white text-black text-sm font-semibold disabled:bg-zinc-800 disabled:text-zinc-400"
                      >
                        Execute Trade
                      </button>
                      <button onClick={() => { setModalTradeAmountYes(0); setModalTradeAmountNo(0); setModalQuote(null); }} className="h-9 px-4 text-sm border border-zinc-700 rounded-xl">
                        Clear
                      </button>
                    </div>

                    {/* Live quote / impact (from /quote) */}
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

                {/* ==================== ADMIN VERSION EXTRAS ==================== */}
                {activeTab === 'admin' && (
                  <div className="border-t border-zinc-700 pt-5 space-y-4">
                    <div className="font-semibold text-lg flex items-center gap-2">
                      Admin Controls — {marketDetail?.title}
                      <span className="text-xs px-2 py-0.5 rounded bg-red-900/30 text-red-300 border border-red-700">ADMIN ONLY</span>
                    </div>

                    {/* Liquidity parameter visibility for admin */}
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

                    {/* Resolve this specific market */}
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
                              await fetchJson(`/admin/markets/${selectedMarketId}/resolve`, {
                                method: 'POST',
                                body: JSON.stringify({ outcome: resolveOutcome }),
                              });
                              setMessage(`Resolved ${selectedMarketId} to ${resolveOutcome} (admin).`);
                              await refreshCurrentMarketDetail();
                              await refreshAll();
                            } catch (e: any) {
                              setMessage('Admin resolve error: ' + e.message);
                            }
                          }}
                          className="px-5 h-9 rounded-xl bg-red-600 hover:bg-red-500 text-sm font-semibold"
                        >
                          Resolve Market (Admin)
                        </button>
                      </div>
                      <div className="text-xs text-zinc-400 mt-1">This affects every user. Payouts and scores are recorded immediately.</div>
                    </div>

                    {/* All users' positions on THIS market (admin only) */}
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

                    {/* Resolution PnL for admin when viewing resolved market */}
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
                <button onClick={closeMarketView} className="underline">Close</button>
              </div>
            </div>
          </div>
        )}

        <div className="mt-12 text-xs text-zinc-500 border-t pt-6">
          Professional separate frontend (Next.js) • Backend: FastAPI on {API_BASE} • 
          Make sure the backend is running (<code>lmsr serve</code> or <code>uvicorn lmsr.api:app --port 8000</code>) and has data (run the 300-round script or a demo scenario).
        </div>
      </div>
    </div>
  );
}
