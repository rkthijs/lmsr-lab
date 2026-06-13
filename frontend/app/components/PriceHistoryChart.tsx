"use client";

import React, { useState } from 'react';

interface Trade {
  user_id?: string;
  shares_yes: number;
  shares_no: number;
  price_after_yes?: number;
  price_after_no?: number;
}

interface PriceHistoryChartProps {
  trades: Trade[];
  onHover?: (idx: number | null) => void;
  hoveredIdx?: number | null;
}

export default function PriceHistoryChart({ trades, onHover, hoveredIdx: externalHovered }: PriceHistoryChartProps) {
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
    const rect = evt.currentTarget.getBoundingClientRect();
    const mx = ((evt.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bestDist = Infinity;
    points.forEach((pt, idx) => {
      const d = Math.abs(pt.x - mx);
      if (d < bestDist) { bestDist = d; best = idx; }
    });
    setHovered(best);
  };

  const onLeave = () => setHovered(null);

  const hoveredPoint = hovered != null ? points[hovered] : null;

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
            r={hovered === idx ? 5 : 2.5}
            fill={hovered === idx ? "#10b981" : "#10b981"}
            stroke={hovered === idx ? "#fff" : "none"}
            strokeWidth={hovered === idx ? 1.5 : 0}
          />
        ))}

        {/* Hover vertical guide + tooltip anchor */}
        {hoveredPoint && (
          <line
            x1={hoveredPoint.x}
            y1={PAD}
            x2={hoveredPoint.x}
            y2={H - PAD}
            stroke="#10b981"
            strokeWidth="1"
            strokeDasharray="3 2"
            opacity="0.6"
          />
        )}
      </svg>

      {/* Tooltip */}
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
        </div>
      )}

      <div className="text-[10px] text-zinc-400 mt-1">
        {series.length - 1} trades • Drag mouse over the chart for exact values. Starts at 0.50 before any trading.
      </div>
    </div>
  );
}
