"use client";

import React from 'react';
import { LeaderboardEntry, LeaderboardMetric } from '../types';

interface LeaderboardProps {
  leaderboard: LeaderboardEntry[];
  metric: LeaderboardMetric;
  loading?: boolean;
  onMetricChange: (m: LeaderboardMetric) => void;
}

export default function Leaderboard({ leaderboard, metric, loading = false, onMetricChange }: LeaderboardProps) {
  const metrics: LeaderboardMetric[] = ['brier', 'log', 'pnl'];

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
              <th className="text-left p-3">User</th>
              <th className="text-right p-3">Resolved Trades</th>
              {metric === 'brier' && <th className="text-right p-3">Avg Brier</th>}
              {metric === 'log' && <th className="text-right p-3">Avg Log Score</th>}
              <th className="text-right p-3">Total PnL</th>
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
              leaderboard.map((entry, idx) => (
                <tr key={idx} className="border-t border-zinc-800 hover:bg-zinc-900/50">
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
        Global across all resolved markets. Lower Brier / higher Log / higher PnL is better. Use metric buttons to switch.
      </div>
    </div>
  );
}
