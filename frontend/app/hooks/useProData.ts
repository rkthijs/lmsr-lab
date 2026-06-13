import { useState, useCallback, useEffect } from 'react';
import { useFetch } from './useFetch';
import {
  User,
  Market,
  ActivityItem,
  Account,
  Portfolio,
  LeaderboardEntry,
  LeaderboardMetric,
  Trade,
  MarketDetail,
  QuoteResponse,
} from '../types';

export function useProData() {
  const { fetchData } = useFetch();

  // All state
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

  const [tradeAmounts, setTradeAmounts] = useState<Record<string, { yes: number; no: number }>>({});

  const [resolveMarketId, setResolveMarketId] = useState('');
  const [resolveOutcome, setResolveOutcome] = useState<'yes' | 'no'>('yes');

  const [scenarios, setScenarios] = useState<string[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>('');

  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [leaderboardMetric, setLeaderboardMetric] = useState<LeaderboardMetric>('brier');

  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [marketDetail, setMarketDetail] = useState<MarketDetail | null>(null);
  const [marketTrades, setMarketTrades] = useState<Trade[]>([]);
  const [marketPositions, setMarketPositions] = useState<Record<string, { yes: number; no: number }>>({});
  const [hoveredTradeIdx, setHoveredTradeIdx] = useState<number | null>(null);
  const [modalTradeAmountYes, setModalTradeAmountYes] = useState(0);
  const [modalTradeAmountNo, setModalTradeAmountNo] = useState(0);
  const [modalQuote, setModalQuote] = useState<QuoteResponse | null>(null);

  // Helper getters/setters for trade amounts
  const getTradeAmount = useCallback((marketId: string, side: 'yes' | 'no') => {
    return tradeAmounts[marketId]?.[side] || 0;
  }, [tradeAmounts]);

  const setTradeAmount = useCallback((marketId: string, side: 'yes' | 'no', val: number) => {
    setTradeAmounts(prev => ({
      ...prev,
      [marketId]: {
        ...(prev[marketId] || { yes: 0, no: 0 }),
        [side]: val
      }
    }));
  }, []);

  // Load functions
  const loadUsers = useCallback(async () => {
    try {
      const data = await fetchData<User[]>('/admin/users');
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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage('Failed to load users: ' + msg + '. Is the backend running on :8000?');
    }
  }, [selectedUser, fetchData]);

  const loadMarkets = useCallback(async () => {
    try {
      const data = await fetchData<Market[]>('/admin/markets');
      setMarkets(data);
    } catch (e: unknown) {
      console.error(e);
    }
  }, [fetchData]);

  const loadActivity = useCallback(async () => {
    try {
      const data = await fetchData<ActivityItem[]>('/admin/activity?limit=100');
      setActivity(data);
    } catch (e: unknown) {
      console.error(e);
    }
  }, [fetchData]);

  const loadUserData = useCallback(async (userId: string) => {
    setLoading(true);
    setMessage('');
    try {
      const [acc, port] = await Promise.all([
        fetchData<Account>(`/users/${userId}/account`),
        fetchData<Portfolio>(`/users/${userId}/portfolio`),
      ]);
      setAccount(acc);
      setPortfolio(port);

      const posMap: Record<string, { yes: number; no: number }> = {};
      for (const m of markets) {
        try {
          const obs = await fetchData<{ position: { yes: number; no: number } }>(`/markets/${m.id}/observe?user_id=${userId}`);
          posMap[m.id] = obs.position;
        } catch {}
      }
      setUserPositions(posMap);
    } catch (e: any) {
      setMessage('Failed to load user data: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [markets, fetchData]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadUsers(), loadMarkets(), loadActivity()]);
    if (selectedUser) await loadUserData(selectedUser);
    await loadLeaderboard(leaderboardMetric);
  }, [loadUsers, loadMarkets, loadActivity, loadUserData, selectedUser, leaderboardMetric]);

  const loadScenarios = useCallback(async () => {
    try {
      const data = await fetchData<{ scenarios?: string[]; error?: string }>('/admin/scenarios');
      const list: string[] = data.scenarios || [];
      setScenarios(list);
      if (list.length > 0 && !selectedScenario) {
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
  }, [selectedScenario, fetchData]);

  const loadLeaderboard = useCallback(async (metric: LeaderboardMetric = leaderboardMetric) => {
    try {
      const data: LeaderboardEntry[] = await fetchData(`/leaderboard?metric=${metric}&min_resolved_trades=1`);
      setLeaderboard(data || []);
    } catch (e: any) {
      console.error(e);
      setLeaderboard([]);
    }
  }, [fetchData, leaderboardMetric]);

  const loadSelectedScenario = useCallback(async () => {
    if (!selectedScenario) return;
    setMessage('Loading demo scenario...');
    try {
      const res = await fetchData<{ message?: string }>('/admin/scenarios/load', {
        method: 'POST',
        body: JSON.stringify({ name: selectedScenario }),
      });
      setMessage(res.message || `Loaded scenario: ${selectedScenario}`);
      closeMarketView();
      await refreshAll();
    } catch (e: any) {
      setMessage('Load scenario failed: ' + e.message);
    }
  }, [selectedScenario, refreshAll]);

  const resetSimulator = useCallback(async () => {
    setMessage('Resetting simulator...');
    try {
      await fetchData('/reset', { method: 'POST' });
      setMessage('Simulator reset to empty state.');
      await refreshAll();
    } catch (e: any) {
      setMessage('Reset failed: ' + e.message);
    }
  }, [refreshAll]);

  // Market detail helpers
  const loadMarketTrades = useCallback(async (marketId: string) => {
    try {
      const trades = await fetchData<Trade[]>(`/markets/${marketId}/trades`);
      setMarketTrades(Array.isArray(trades) ? trades : []);
    } catch (e: any) {
      setMarketTrades([]);
    }
  }, [fetchData]);

  const loadMarketDetail = useCallback(async (marketId: string) => {
    try {
      const path = activeTab === 'admin' ? `/admin/markets/${marketId}` : `/markets/${marketId}`;
      const m = await fetchData<MarketDetail>(path);
      setMarketDetail(m);
    } catch (e: any) {
      setMarketDetail(null);
    }
  }, [activeTab, fetchData]);

  const loadAdminMarketPositions = useCallback(async (marketId: string) => {
    if (users.length === 0) return;
    const posMap: Record<string, { yes: number; no: number }> = {};
    await Promise.all(users.map(async (u) => {
      try {
        const obs = await fetchData<{ position: { yes: number; no: number } }>(`/markets/${marketId}/observe?user_id=${u.user_id}`);
        posMap[u.user_id] = obs.position || { yes: 0, no: 0 };
      } catch {
        posMap[u.user_id] = { yes: 0, no: 0 };
      }
    }));
    setMarketPositions(posMap);
  }, [users, fetchData]);

  const openMarketView = useCallback(async (marketId: string) => {
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
  }, [loadMarketDetail, loadMarketTrades, loadAdminMarketPositions, activeTab]);

  const closeMarketView = useCallback(() => {
    setSelectedMarketId(null);
    setMarketDetail(null);
    setMarketTrades([]);
    setMarketPositions({});
    setHoveredTradeIdx(null);
    setModalTradeAmountYes(0);
    setModalTradeAmountNo(0);
    setModalQuote(null);
  }, []);

  const refreshCurrentMarketDetail = useCallback(async () => {
    if (!selectedMarketId) return;
    await Promise.all([
      loadMarketDetail(selectedMarketId),
      loadMarketTrades(selectedMarketId),
    ]);
    if (activeTab === 'admin') {
      await loadAdminMarketPositions(selectedMarketId);
    }
  }, [selectedMarketId, loadMarketDetail, loadMarketTrades, loadAdminMarketPositions, activeTab]);

  const updateModalQuote = useCallback(async (yesDelta: number, noDelta: number) => {
    if (!selectedMarketId) return;
    if (yesDelta === 0 && noDelta === 0) {
      setModalQuote(null);
      return;
    }
    try {
      const q = await fetchData<import('../types').QuoteResponse>(
        `/markets/${selectedMarketId}/quote?shares_yes=${yesDelta}&shares_no=${noDelta}`
      );
      setModalQuote(q);
    } catch {
      setModalQuote(null);
    }
  }, [selectedMarketId, fetchData]);

  const doModalTrade = useCallback(async () => {
    if (!selectedMarketId) return;
    const y = modalTradeAmountYes;
    const n = modalTradeAmountNo;
    if (y === 0 && n === 0) return;
    try {
      await doTrade(selectedMarketId, y, n);
      setModalTradeAmountYes(0);
      setModalTradeAmountNo(0);
      setModalQuote(null);
      await refreshCurrentMarketDetail();
    } catch (e: any) {
      setMessage('Modal trade error: ' + e.message);
    }
  }, [selectedMarketId, modalTradeAmountYes, modalTradeAmountNo, refreshCurrentMarketDetail]);

  // Main doTrade
  const doTrade = useCallback(async (marketId: string, yesDelta: number, noDelta: number) => {
    if (yesDelta === 0 && noDelta === 0) return;
    setMessage('');
    try {
      const res = await fetchData<{ error?: string; cost?: number; fee?: number }>(`/markets/${marketId}/trades`, {
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
        setTradeAmounts(prev => ({ ...prev, [marketId]: { yes: 0, no: 0 } }));
        await refreshAll();
        if (selectedMarketId === marketId) {
          await refreshCurrentMarketDetail();
        }
      }
    } catch (e: any) {
      setMessage('Trade error: ' + e.message);
    }
  }, [selectedUser, refreshAll, selectedMarketId, refreshCurrentMarketDetail]);

  const doResolve = useCallback(async () => {
    if (!resolveMarketId) return;
    setMessage('');
    try {
      const res = await fetchData<{ error?: string }>(`/admin/markets/${resolveMarketId}/resolve`, {
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
  }, [resolveMarketId, resolveOutcome, refreshAll, selectedMarketId, refreshCurrentMarketDetail]);

  // Computed
  const openMarkets = markets.filter(m => m.status === 'open');
  const resolvedMarkets = markets.filter(m => m.status === 'resolved');

  // Effects
  useEffect(() => {
    refreshAll();
    loadScenarios();
  }, []);

  useEffect(() => {
    if (selectedUser) {
      loadUserData(selectedUser);
    }
  }, [selectedUser, markets]);

  useEffect(() => {
    if (activeTab === 'admin') {
      loadScenarios();
      loadLeaderboard(leaderboardMetric);
    }
  }, [activeTab, leaderboardMetric]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && selectedMarketId) {
        // closeMarketView is defined below, but for hook we can expose
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedMarketId]);

  useEffect(() => {
    if (selectedMarketId) {
      updateModalQuote(modalTradeAmountYes, modalTradeAmountNo);
    }
  }, [modalTradeAmountYes, modalTradeAmountNo, selectedMarketId, updateModalQuote]);

  // Expose close for key, but since effect is here, we can move close logic
  const closeMarketViewHook = useCallback(() => {
    setSelectedMarketId(null);
    setMarketDetail(null);
    setMarketTrades([]);
    setMarketPositions({});
    setHoveredTradeIdx(null);
    setModalTradeAmountYes(0);
    setModalTradeAmountNo(0);
    setModalQuote(null);
  }, []);

  // Update the key effect to use local
  // (in real, effects would use the exposed close)

  return {
    // all state and setters
    selectedUser, setSelectedUser,
    users, markets, activity, account, portfolio, userPositions,
    loading, message, setMessage, activeTab, setActiveTab,
    tradeAmounts, setTradeAmounts,
    resolveMarketId, setResolveMarketId, resolveOutcome, setResolveOutcome,
    scenarios, setScenarios, selectedScenario, setSelectedScenario,
    leaderboard, setLeaderboard, leaderboardMetric, setLeaderboardMetric,
    selectedMarketId, setSelectedMarketId,
    marketDetail, setMarketDetail,
    marketTrades, setMarketTrades,
    marketPositions, setMarketPositions,
    hoveredTradeIdx, setHoveredTradeIdx,
    modalTradeAmountYes, setModalTradeAmountYes,
    modalTradeAmountNo, setModalTradeAmountNo,
    modalQuote, setModalQuote,

    // functions
    getTradeAmount,
    setTradeAmount,
    loadUsers, loadMarkets, loadActivity, loadUserData, refreshAll,
    loadScenarios, loadLeaderboard, loadSelectedScenario, resetSimulator,
    loadMarketTrades, loadMarketDetail, loadAdminMarketPositions,
    openMarketView, closeMarketView: closeMarketViewHook,
    refreshCurrentMarketDetail, updateModalQuote, doModalTrade,
    doTrade, doResolve,

    // computed
    openMarkets, resolvedMarkets,
  };
}
