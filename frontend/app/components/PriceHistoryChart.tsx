"use client";

import React, { useState } from 'react';

interface Trade {
  user_id?: string;
  shares_yes: number;
  shares_no: number;
  price_after_yes?: number;
  price_after_no?: number;
  mm_profit?: number;
}

interface PriceHistoryChartProps {
  trades: Trade[];
  onHover?: (idx: number | null) => void;
  hoveredIdx?: number | null;
  showMmProfit?: boolean;
}

export default function PriceHistoryChart({ trades, onHover, hoveredIdx: externalHovered, showMmProfit = false }: PriceHistoryChartProps) {
  const [internalHovered, setInternalHovered] = useState<number | null>(null);
  const hovered = externalHovered !== undefined ? externalHovered : internalHovered;
  const setHovered = onHover || setInternalHovered;

  const series = [0.5];
  trades.forEach((t) => {
    if (typeof t.price_after_yes === 'number') series.push(t.price_after_yes);
  });
  const n = series.length;
  if (n < 2) {
    return <div className="text-sm text-zinc-400 bg-zinc-900 border border-zinc-800 rounded-2xl p-6">No trades yet — the market starts at 50/50. Make the first trade to see the time series.</div>;
  }

  // mm profit series (one per executed trade, aligns with price points[1..])
  const mmProfits: number[] = [];
  if (showMmProfit) {
    trades.forEach((t) => {
      if (typeof (t as any).mm_profit === 'number') mmProfits.push((t as any).mm_profit);
    });
  }
  const hasMmProfit = showMmProfit && mmProfits.length > 0 && mmProfits.length === trades.length;

  const W = 820;
  const PAD = 36;
  const PRICE_H = 200;
  const PROFIT_H = hasMmProfit ? 106 : 0;
  const GAP = hasMmProfit ? 22 : 0;
  const H = PAD * 2 + PRICE_H + GAP + PROFIT_H;

  const CHART_W = W - PAD * 2;
  const priceChartH = PRICE_H;

  const points = series.map((p, i) => {
    const x = PAD + (n > 1 ? (i / (n - 1)) * CHART_W : 0);
    const y = PAD + (1 - Math.max(0, Math.min(1, p))) * priceChartH;
    return { x, y, p, i };
  });

  const pathD = points.map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');

  // Profit scale + mapping (only if shown)
  let profitMin = 0;
  let profitMax = 0;
  if (hasMmProfit) {
    profitMin = Math.min(...mmProfits, 0);
    profitMax = Math.max(...mmProfits, 0);
    const pr = Math.max(1e-6, profitMax - profitMin);
    profitMin -= pr * 0.12;
    profitMax += pr * 0.12;
  }
  const profitBandTop = PAD + priceChartH + GAP;
  const profitChartH = PROFIT_H;

  const profitY = (v: number) => {
    if (!hasMmProfit || profitMax === profitMin) return profitBandTop + profitChartH / 2;
    const f = (v - profitMin) / (profitMax - profitMin);
    return profitBandTop + (1 - Math.max(0, Math.min(1, f))) * profitChartH;
  };

  const profitPoints = hasMmProfit
    ? mmProfits.map((val, k) => {
        const pi = k + 1; // align to price series (post-trade point)
        const x = points[pi] ? points[pi].x : PAD + CHART_W;
        const y = profitY(val);
        return { x, y, val, i: pi };
      })
    : [];

  const pathDProfit =
    profitPoints.length > 1
      ? profitPoints.map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ')
      : '';

  const onMove = (evt: React.MouseEvent<SVGSVGElement>) => {
    const rect = evt.currentTarget.getBoundingClientRect();
    const mx = ((evt.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bestDist = Infinity;
    points.forEach((pt, idx) => {
      const d = Math.abs(pt.x - mx);
      if (d < bestDist) {
        bestDist = d;
        best = idx;
      }
    });
    setHovered(best);
  };

  const onLeave = () => setHovered(null);

  const hoveredPoint = hovered != null ? points[hovered] : null;

  // For tooltip: if we have a hovered trade point (>=1) and mm data, include the corresponding mm_profit
  const hoveredMm = hovered != null && hasMmProfit && hovered >= 1 ? mmProfits[hovered - 1] : null;

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
        {/* Price band: Grid + Y labels (fixed 0-1) */}
        {[0, 0.25, 0.5, 0.75, 1].map((v, i) => {
          const y = PAD + (1 - v) * priceChartH;
          return (
            <g key={i}>
              <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="#3f3f46" strokeWidth="1" />
              <text x={PAD - 6} y={y + 4} fill="#71717a" fontSize="11" textAnchor="end">{v.toFixed(1)}</text>
            </g>
          );
        })}

        {/* Profit band: 0-line + a few value ticks (auto-scaled) */}
        {hasMmProfit && (
          <g>
            <line
              x1={PAD}
              y1={profitY(0)}
              x2={W - PAD}
              y2={profitY(0)}
              stroke="#3f3f46"
              strokeWidth="1"
              strokeDasharray="3 2"
            />
            {/* light ticks at extremes + zero for orientation */}
            {[profitMin, 0, profitMax]
              .filter((v, idx, arr) => arr.findIndex((av) => Math.abs(av - v) < 1e-9) === idx)
              .map((v, i) => {
                const y = profitY(v);
                return (
                  <g key={i}>
                    <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="#27272a" strokeWidth="0.5" />
                    <text x={PAD - 6} y={y + 3} fill="#52525b" fontSize="9" textAnchor="end">
                      {v.toFixed(2)}
                    </text>
                  </g>
                );
              })}
          </g>
        )}

        {/* X axis label (at very bottom) */}
        <text x={W / 2} y={H - 6} fill="#71717a" fontSize="11" textAnchor="middle">
          Trade # (sequence of executed trades)
        </text>

        {/* The price path line (emerald like Kalshi Yes) */}
        <path d={pathD} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />

        {/* Price dots + hover highlight */}
        {points.map((pt, idx) => (
          <circle
            key={idx}
            cx={pt.x}
            cy={pt.y}
            r={hovered === idx ? 5 : 2.5}
            fill={hovered === idx ? "#10b981" : "#10b981"}
            stroke={hovered === idx ? "#fff" : "none"}
            strokeWidth={hovered === idx ? 1.5 : 0}
          />
        ))}

        {/* Profit path + dots (violet for house/MM) */}
        {hasMmProfit && pathDProfit && (
          <>
            <path
              d={pathDProfit}
              fill="none"
              stroke="#a78bfa"
              strokeWidth="2.25"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {profitPoints.map((pt, idx) => (
              <circle
                key={`mm-${idx}`}
                cx={pt.x}
                cy={pt.y}
                r={hovered === pt.i ? 4 : 2}
                fill={hovered === pt.i ? "#c4b5fd" : "#a78bfa"}
                stroke={hovered === pt.i ? "#fff" : "none"}
                strokeWidth={hovered === pt.i ? 1.25 : 0}
              />
            ))}
          </>
        )}

        {/* Hover vertical guide spans the full (price + profit) area */}
        {hoveredPoint && (
          <line
            x1={hoveredPoint.x}
            y1={PAD}
            x2={hoveredPoint.x}
            y2={H - PAD}
            stroke={hasMmProfit ? "#64748b" : "#10b981"}
            strokeWidth="1"
            strokeDasharray="3 2"
            opacity="0.55"
          />
        )}

        {/* Small section label for the lower band */}
        {hasMmProfit && (
          <text x={PAD + 4} y={profitBandTop - 5} fill="#a1a1aa" fontSize="10">
            MM running P/L (admin)
          </text>
        )}
      </svg>

      {/* Tooltip — shows price and (when available + admin) the mm_profit at that step */}
      {hoveredPoint && (
        <div
          className="absolute bg-zinc-800 border border-emerald-500/50 text-xs px-3 py-1 rounded shadow pointer-events-none"
          style={{
            left: `${((hoveredPoint.x / W) * 100).toFixed(1)}%`,
            top: 12,
            transform: 'translate(-50%, 0)'
          }}
        >
          Trade #{hoveredPoint.i} • P(Yes) = <span className="font-semibold text-emerald-400">{(hoveredPoint.p * 100).toFixed(1)}¢</span>
          {hoveredMm != null && (
            <>
              {' '}
              • MM P/L <span className="font-semibold text-violet-400">{hoveredMm.toFixed(2)}</span>
            </>
          )}
        </div>
      )}

      <div className="text-[10px] text-zinc-400 mt-1">
        {series.length - 1} trades • Drag mouse over the chart for exact values. Starts at 0.50 before any trading.
        {hasMmProfit && '  • Lower track: running market-maker P/L (admin view only).'}
      </div>
    </div>
  );
}
