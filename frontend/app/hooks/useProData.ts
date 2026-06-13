import { useState, useCallback, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from './useFetch';
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
  const queryClient = useQueryClient();

  // === UI-only / transient state (not server-cached by RQ) ===
  const [selectedUser, setSelectedUser] = useState<string>('bull');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState<'user' | 'admin'>('user');

  const [tradeAmounts, setTradeAmounts] = useState<Record<string, { yes: number; no: number }>>({});

  const [resolveMarketId, setResolveMarketId] = useState('');
  const [resolveOutcome, setResolveOutcome] = useState<'yes' | 'no'>('yes');

  const [selectedScenario, setSelectedScenario] = useState<string>('');

  const [leaderboardMetric, setLeaderboardMetric] = useState<LeaderboardMetric>('brier');

  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [hoveredTradeIdx, setHoveredTradeIdx] = useState<number | null>(null);
  const [modalTradeAmountYes, setModalTradeAmountYes] = useState(0);
  const [modalTradeAmountNo, setModalTradeAmountNo] = useState(0);
  const [modalQuote, setModalQuote] = useState<QuoteResponse | null>(null);

  // Modal-specific local state (synced from queries below)
  const [marketTrades, setMarketTrades] = useState<Trade[]>([]);
  const [marketPositions, setMarketPositions] = useState<Record<string, { yes: number; no: number }>>({});

  // === React Query backed data ===
  const usersQuery = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/admin/users'),
  });

  const marketsQuery = useQuery<Market[]>({
    queryKey: ['markets'],
    queryFn: () => apiFetch<Market[]>('/admin/markets'),
  });

  const activityQuery = useQuery<ActivityItem[]>({
    queryKey: ['activity'],
    queryFn: () => apiFetch<ActivityItem[]>('/admin/activity?limit=100'),
  });

  const scenariosQuery = useQuery<{ scenarios?: string[]; error?: string }>({
    queryKey: ['scenarios'],
    queryFn: () => apiFetch('/admin/scenarios'),
  });

  const leaderboardQuery = useQuery<LeaderboardEntry[]>({
    queryKey: ['leaderboard', leaderboardMetric],
    queryFn: () => apiFetch<LeaderboardEntry[]>(`/leaderboard?metric=${leaderboardMetric}&min_resolved_trades=1`),
  });

  const accountQuery = useQuery<Account | null>({
    queryKey: ['account', selectedUser],
    enabled: !!selectedUser,
    queryFn: () => apiFetch<Account>(`/users/${selectedUser}/account`),
  });

  const portfolioQuery = useQuery<Portfolio | null>({
    queryKey: ['portfolio', selectedUser],
    enabled: !!selectedUser,
    queryFn: () => apiFetch<Portfolio>(`/users/${selectedUser}/portfolio`),
  });

  // Derived (stable for page/components)
  const users = usersQuery.data ?? [];
  const markets = marketsQuery.data ?? [];
  const activity = activityQuery.data ?? [];
  const leaderboard = leaderboardQuery.data ?? [];
  const account = accountQuery.data ?? null;
  const portfolio = portfolioQuery.data ?? null;

  const [userPositions, setUserPositions] = useState<Record<string, { yes: number; no: number }>>({});

  const scenarios: string[] = scenariosQuery.data?.scenarios || [];

  // === Trade amount helpers (unchanged API) ===
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

  // === Positions (small N observe calls; manual but uses shared apiFetch) ===
  const loadUserPositions = useCallback(async (userId: string, mList: Market[]) => {
    const posMap: Record<string, { yes: number; no: number }> = {};
    await Promise.all(mList.map(async (m) => {
      try {
        const obs = await apiFetch<{ position: { yes: number; no: number } }>(`/markets/${m.id}/observe?user_id=${userId}`);
        posMap[m.id] = obs.position;
      } catch {
        posMap[m.id] = { yes: 0, no: 0 };
      }
    }));
    setUserPositions(posMap);
  }, []);

  // === Invalidation + refresh ===
  const invalidateCore = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['users'] });
    queryClient.invalidateQueries({ queryKey: ['markets'] });
    queryClient.invalidateQueries({ queryKey: ['activity'] });
    queryClient.invalidateQueries({ queryKey: ['leaderboard'] });
  }, [queryClient]);

  const refreshAll = useCallback(async () => {
    invalidateCore();
    if (selectedUser) {
      queryClient.invalidateQueries({ queryKey: ['account', selectedUser] });
      queryClient.invalidateQueries({ queryKey: ['portfolio', selectedUser] });
    }
  }, [invalidateCore, selectedUser, queryClient]);

  const loadScenarios = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['scenarios'] });
  }, [queryClient]);

  const loadLeaderboard = useCallback((metric: LeaderboardMetric = leaderboardMetric) => {
    if (metric !== leaderboardMetric) setLeaderboardMetric(metric);
    queryClient.invalidateQueries({ queryKey: ['leaderboard'] });
  }, [queryClient, leaderboardMetric]);

  // === Mutations (POSTs that change server state) ===
  const tradeMutation = useMutation({
    mutationFn: async (vars: { marketId: string; yesDelta: number; noDelta: number }) => {
      return apiFetch<{ error?: string; cost?: number; fee?: number }>(`/markets/${vars.marketId}/trades`, {
        method: 'POST',
        body: JSON.stringify({ user_id: selectedUser, shares_yes: vars.yesDelta, shares_no: vars.noDelta }),
      });
    },
    onSuccess: (res, vars) => {
      if (res.error) {
        setMessage(`Trade failed: ${res.error}`);
      } else {
        setMessage(`Trade executed. Cost: ${res.cost?.toFixed(2)} (fee ${res.fee?.toFixed(2) || '0.00'})`);
        setTradeAmounts(prev => ({ ...prev, [vars.marketId]: { yes: 0, no: 0 } }));
        invalidateCore();
        queryClient.invalidateQueries({ queryKey: ['account', selectedUser] });
        queryClient.invalidateQueries({ queryKey: ['portfolio', selectedUser] });
        if (selectedMarketId === vars.marketId) {
          queryClient.invalidateQueries({ queryKey: ['marketDetail', selectedMarketId] });
          queryClient.invalidateQueries({ queryKey: ['marketTrades', selectedMarketId] });
        }
      }
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage('Trade error: ' + msg);
    },
  });

  const doTrade = useCallback(async (marketId: string, yesDelta: number, noDelta: number) => {
    if (yesDelta === 0 && noDelta === 0) return;
    setMessage('');
    tradeMutation.mutate({ marketId, yesDelta, noDelta });
  }, [tradeMutation]);

  const resolveMutation = useMutation({
    mutationFn: async (vars: { marketId: string; outcome: 'yes' | 'no' }) => {
      return apiFetch<{ error?: string }>(`/admin/markets/${vars.marketId}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ outcome: vars.outcome }),
      });
    },
    onSuccess: (_res, vars) => {
      setMessage(`Market ${vars.marketId} resolved to ${vars.outcome}.`);
      invalidateCore();
      queryClient.invalidateQueries({ queryKey: ['account', selectedUser] });
      queryClient.invalidateQueries({ queryKey: ['portfolio', selectedUser] });
      if (selectedMarketId === vars.marketId) {
        queryClient.invalidateQueries({ queryKey: ['marketDetail', selectedMarketId] });
        queryClient.invalidateQueries({ queryKey: ['marketTrades', selectedMarketId] });
      }
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage('Resolve error: ' + msg);
    },
  });

  const doResolve = useCallback(async () => {
    if (!resolveMarketId) return;
    setMessage('');
    resolveMutation.mutate({ marketId: resolveMarketId, outcome: resolveOutcome });
  }, [resolveMarketId, resolveOutcome, resolveMutation]);

  const loadScenarioMutation = useMutation({
    mutationFn: async (name: string) => {
      return apiFetch<{ message?: string }>('/admin/scenarios/load', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
    },
    onSuccess: (res, name) => {
      setMessage(res.message || `Loaded scenario: ${name}`);
      closeMarketView();
      invalidateCore();
      queryClient.invalidateQueries({ queryKey: ['account', selectedUser] });
      queryClient.invalidateQueries({ queryKey: ['portfolio', selectedUser] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage('Load scenario failed: ' + msg);
    },
  });

  const loadSelectedScenario = useCallback(async () => {
    if (!selectedScenario) return;
    setMessage('Loading demo scenario...');
    loadScenarioMutation.mutate(selectedScenario);
  }, [selectedScenario, loadScenarioMutation]);

  const resetMutation = useMutation({
    mutationFn: async () => {
      return apiFetch('/reset', { method: 'POST' });
    },
    onSuccess: () => {
      setMessage('Simulator reset to empty state.');
      invalidateCore();
      queryClient.invalidateQueries({ queryKey: ['account', selectedUser] });
      queryClient.invalidateQueries({ queryKey: ['portfolio', selectedUser] });
      setUserPositions({});
      closeMarketView();
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage('Reset failed: ' + msg);
    },
  });

  const resetSimulator = useCallback(async () => {
    setMessage('Resetting simulator...');
    resetMutation.mutate();
  }, [resetMutation]);

  // === Modal-specific queries (auto-fetch when selectedMarketId changes) ===
  const marketDetailQuery = useQuery<MarketDetail | null>({
    queryKey: ['marketDetail', selectedMarketId, activeTab],
    enabled: !!selectedMarketId,
    queryFn: () => {
      if (!selectedMarketId) return Promise.resolve(null as MarketDetail | null);
      const path = activeTab === 'admin' ? `/admin/markets/${selectedMarketId}` : `/markets/${selectedMarketId}`;
      return apiFetch<MarketDetail>(path);
    },
  });

  const marketTradesQuery = useQuery<Trade[]>({
    queryKey: ['marketTrades', selectedMarketId],
    enabled: !!selectedMarketId,
    queryFn: () => {
      if (!selectedMarketId) return Promise.resolve([]);
      return apiFetch<Trade[]>(`/markets/${selectedMarketId}/trades`);
    },
  });

  useEffect(() => {
    setMarketTrades(marketTradesQuery.data ?? []);
  }, [marketTradesQuery.data]);

  const marketDetail = marketDetailQuery.data ?? null;

  // === Admin cross-user positions (small, on-demand) ===
  const loadAdminMarketPositions = useCallback(async (marketId: string) => {
    if (users.length === 0) return;
    const posMap: Record<string, { yes: number; no: number }> = {};
    await Promise.all(users.map(async (u) => {
      try {
        const obs = await apiFetch<{ position: { yes: number; no: number } }>(`/markets/${marketId}/observe?user_id=${u.user_id}`);
        posMap[u.user_id] = obs.position || { yes: 0, no: 0 };
      } catch {
        posMap[u.user_id] = { yes: 0, no: 0 };
      }
    }));
    setMarketPositions(posMap);
  }, [users]);

  // === Modal open/close (setting id enables the queries above) ===
  const openMarketView = useCallback(async (marketId: string) => {
    setSelectedMarketId(marketId);
    setHoveredTradeIdx(null);
    setModalTradeAmountYes(0);
    setModalTradeAmountNo(0);
    setModalQuote(null);
    setMarketPositions({});

    if (activeTab === 'admin') {
      loadAdminMarketPositions(marketId);
    }
  }, [activeTab, loadAdminMarketPositions]);

  const closeMarketView = useCallback(() => {
    setSelectedMarketId(null);
    setMarketTrades([]);
    setMarketPositions({});
    setHoveredTradeIdx(null);
    setModalTradeAmountYes(0);
    setModalTradeAmountNo(0);
    setModalQuote(null);
  }, []);

  const refreshCurrentMarketDetail = useCallback(async () => {
    if (!selectedMarketId) return;
    queryClient.invalidateQueries({ queryKey: ['marketDetail', selectedMarketId, activeTab] });
    queryClient.invalidateQueries({ queryKey: ['marketTrades', selectedMarketId] });
    if (activeTab === 'admin') {
      await loadAdminMarketPositions(selectedMarketId);
    }
  }, [selectedMarketId, activeTab, queryClient, loadAdminMarketPositions]);

  const updateModalQuote = useCallback(async (yesDelta: number, noDelta: number) => {
    if (!selectedMarketId) return;
    if (yesDelta === 0 && noDelta === 0) {
      setModalQuote(null);
      return;
    }
    try {
      const q = await apiFetch<QuoteResponse>(
        `/markets/${selectedMarketId}/quote?shares_yes=${yesDelta}&shares_no=${noDelta}`
      );
      setModalQuote(q);
    } catch {
      setModalQuote(null);
    }
  }, [selectedMarketId]);

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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage('Modal trade error: ' + msg);
    }
  }, [selectedMarketId, modalTradeAmountYes, modalTradeAmountNo, doTrade, refreshCurrentMarketDetail]);

  // === Computed (same as before) ===
  const openMarkets = markets.filter(m => m.status === 'open');
  const resolvedMarkets = markets.filter(m => m.status === 'resolved');

  // === Effects: defaults, positions, errors, tab, keyboard, live quote ===
  useEffect(() => {
    if (users.length > 0) {
      const preferred = ['bull', 'contrarian', 'trend', 'random'];
      const foundPreferred = preferred.find(p => users.some(u => u.user_id === p));
      if (foundPreferred && !users.find(u => u.user_id === selectedUser)) {
        setSelectedUser(foundPreferred);
      } else if (!users.find(u => u.user_id === selectedUser)) {
        setSelectedUser(users[0].user_id);
      }
    }
  }, [users, selectedUser]);

  useEffect(() => {
    if (selectedUser && markets.length > 0) {
      loadUserPositions(selectedUser, markets);
    }
  }, [selectedUser, markets, loadUserPositions]);

  useEffect(() => {
    if (scenarios.length > 0 && !selectedScenario) {
      const preferred = scenarios.find(s => s.includes('300') || s.includes('Bot')) || scenarios[0];
      setSelectedScenario(preferred);
    }
    if (scenariosQuery.data?.error) {
      setMessage('Scenarios failed to load: ' + scenariosQuery.data.error);
    }
  }, [scenarios, selectedScenario, scenariosQuery.data]);

  useEffect(() => {
    if (usersQuery.error) {
      const msg = usersQuery.error instanceof Error ? usersQuery.error.message : String(usersQuery.error);
      setMessage('Failed to load users: ' + msg + '. Is the backend running on :8000?');
    }
  }, [usersQuery.error]);

  useEffect(() => {
    if (activeTab === 'admin') {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] });
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] });
    }
  }, [activeTab, queryClient]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && selectedMarketId) {
        closeMarketView();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedMarketId, closeMarketView]);

  useEffect(() => {
    if (selectedMarketId) {
      updateModalQuote(modalTradeAmountYes, modalTradeAmountNo);
    }
  }, [modalTradeAmountYes, modalTradeAmountNo, selectedMarketId, updateModalQuote]);

  // Return shape is intentionally compatible with prior version (page/components unchanged)
  return {
    // state + setters (query-backed data are readonly derived; setters for query data are no-ops)
    selectedUser, setSelectedUser,
    users, markets, activity, account, portfolio, userPositions,
    loading, message, setMessage, activeTab, setActiveTab,
    tradeAmounts, setTradeAmounts,
    resolveMarketId, setResolveMarketId, resolveOutcome, setResolveOutcome,
    scenarios, setScenarios: () => {}, selectedScenario, setSelectedScenario,
    leaderboard, setLeaderboard: () => {}, leaderboardMetric, setLeaderboardMetric,
    selectedMarketId, setSelectedMarketId,
    marketDetail, setMarketDetail: () => {},
    marketTrades, setMarketTrades,
    marketPositions, setMarketPositions,
    hoveredTradeIdx, setHoveredTradeIdx,
    modalTradeAmountYes, setModalTradeAmountYes,
    modalTradeAmountNo, setModalTradeAmountNo,
    modalQuote, setModalQuote,

    // functions (many now delegate to RQ invalidation / mutations)
    getTradeAmount,
    setTradeAmount,
    loadUsers: () => { queryClient.invalidateQueries({ queryKey: ['users'] }); },
    loadMarkets: () => { queryClient.invalidateQueries({ queryKey: ['markets'] }); },
    loadActivity: () => { queryClient.invalidateQueries({ queryKey: ['activity'] }); },
    loadUserData: (userId?: string) => {
      const uid = userId || selectedUser;
      if (uid) {
        queryClient.invalidateQueries({ queryKey: ['account', uid] });
        queryClient.invalidateQueries({ queryKey: ['portfolio', uid] });
      }
    },
    refreshAll,
    loadScenarios,
    loadLeaderboard,
    loadSelectedScenario,
    resetSimulator,
    loadMarketTrades: (id?: string) => { if (id) queryClient.invalidateQueries({ queryKey: ['marketTrades', id] }); },
    loadMarketDetail: (id?: string) => { if (id) queryClient.invalidateQueries({ queryKey: ['marketDetail', id] }); },
    loadAdminMarketPositions,
    openMarketView,
    closeMarketView,
    refreshCurrentMarketDetail,
    updateModalQuote,
    doModalTrade,
    doTrade,
    doResolve,

    // computed
    openMarkets, resolvedMarkets,
  };
}
