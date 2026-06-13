"use client";

import React, { useState, useEffect } from 'react';
import { LeaderboardEntry, LeaderboardMetric } from '../types';

interface LeaderboardProps {
  leaderboard: LeaderboardEntry[];
  metric: LeaderboardMetric;
  loading?: boolean;
  onMetricChange: (m: LeaderboardMetric) => void;
}

export default function Leaderboard({ leaderboard, metric, loading = false, onMetricChange }: LeaderboardProps) {
  const metrics: LeaderboardMetric[] = ['brier', 'log', 'pnl'];

  // Client-side sorting for the leaderboard table (similar to All Users)
  const [sortKey, setSortKey] = useState<'user_id' | 'resolved_trades' | 'score' | 'total_pnl'>('total_pnl');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      if (key === 'score') {
        setSortDir(metric === 'brier' ? 'asc' : 'desc');
      } else if (key === 'user_id') {
        setSortDir('asc');
      } else {
        setSortDir('desc');
      }
    }
  };

  // Auto-adjust score sort direction when metric changes (lower-brier vs higher-others)
  useEffect(() => {
    if (sortKey === 'score') {
      setSortDir(metric === 'brier' ? 'asc' : 'desc');
    }
  }, [metric, sortKey]);

  const sortedLeaderboard = [...leaderboard].sort((a, b) => {
    let va: number | string;
    let vb: number | string;

    if (sortKey === 'user_id') {
      va = a.user_id;
      vb = b.user_id;
    } else if (sortKey === 'resolved_trades') {
      va = a.resolved_trades;
      vb = b.resolved_trades;
    } else if (sortKey === 'score') {
      if (metric === 'brier') {
        va = a.avg_brier ?? Infinity; // missing = very bad (high brier)
        vb = b.avg_brier ?? Infinity;
      } else {
        va = a.avg_log_score ?? -Infinity;
        vb = b.avg_log_score ?? -Infinity;
      }
    } else {
      va = a.total_pnl;
      vb = b.total_pnl;
    }

    if (typeof va === 'string') {
      const cmp = va.localeCompare(vb as string);
      return sortDir === 'asc' ? cmp : -cmp;
    }
    const cmp = (va as number) - (vb as number);
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const sortIndicator = (key: typeof sortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '';

  return (
    <div>
      <h2 className="text-xl font-semibold mb-3">Global Leaderboard</h2>
      <div className="flex gap-2 mb-3 text-sm">
        {metrics.map(m => (
          <button
            key={m}
            onClick={() => onMetricChange(m)}
            className={`px-3 py-1 rounded border transition ${metric === m ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-zinc-700 hover:bg-zinc-800'}`}
          >
            {m === 'brier' ? 'Brier (lower better)' : m === 'log' ? 'Log Score (higher better)' : 'PnL (higher better)'}
          </button>
        ))}
      </div>
      <div className="overflow-auto border border-zinc-800 rounded-2xl max-h-[300px]">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 sticky top-0">
            <tr>
              <th className="text-left p-3">Rank</th>
              <th
                className="text-left p-3 cursor-pointer hover:bg-zinc-800 select-none"
                onClick={() => toggleSort('user_id')}
              >
                User{sortIndicator('user_id')}
              </th>
              <th
                className="text-right p-3 cursor-pointer hover:bg-zinc-800 select-none"
                onClick={() => toggleSort('resolved_trades')}
              >
                Resolved Trades{sortIndicator('resolved_trades')}
              </th>
              {metric === 'brier' && (
                <th
                  className="text-right p-3 cursor-pointer hover:bg-zinc-800 select-none"
                  onClick={() => toggleSort('score')}
                >
                  Avg Brier{sortIndicator('score')}
                </th>
              )}
              {metric === 'log' && (
                <th
                  className="text-right p-3 cursor-pointer hover:bg-zinc-800 select-none"
                  onClick={() => toggleSort('score')}
                >
                  Avg Log Score{sortIndicator('score')}
                </th>
              )}
              <th
                className="text-right p-3 cursor-pointer hover:bg-zinc-800 select-none"
                onClick={() => toggleSort('total_pnl')}
              >
                Total PnL{sortIndicator('total_pnl')}
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && leaderboard.length === 0 ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-t border-zinc-800">
                  {Array.from({ length: metric === 'pnl' ? 4 : 5 }).map((__, j) => (
                    <td key={j} className="p-3"><div className="h-3 bg-zinc-800 animate-pulse rounded" /></td>
                  ))}
                </tr>
              ))
            ) : leaderboard.length === 0 ? (
              <tr>
                <td colSpan={metric === 'pnl' ? 4 : 5} className="p-3 text-zinc-400">
                  No resolved trades yet with scores. Load "Full Teaching Demo (Multi-Market)" or resolve some markets.
                </td>
              </tr>
            ) : (
              sortedLeaderboard.map((entry, idx) => (
                <tr key={entry.user_id} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                  <td className="p-3">{idx + 1}</td>
                  <td className="p-3 font-medium">{entry.user_id}</td>
                  <td className="p-3 text-right tabular-nums">{entry.resolved_trades}</td>
                  {metric === 'brier' && <td className="p-3 text-right tabular-nums">{entry.avg_brier?.toFixed(4)}</td>}
                  {metric === 'log' && <td className="p-3 text-right tabular-nums">{entry.avg_log_score?.toFixed(4)}</td>}
                  <td className="p-3 text-right tabular-nums text-emerald-400">{entry.total_pnl?.toFixed(2)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-zinc-500 mt-1">
        Global across all resolved markets. Lower Brier / higher Log / higher PnL is better. Click column headers to sort. Use metric buttons to switch scoring view.
      </div>
    </div>
  );
}
