"use client";

import React from 'react';
import { Market } from '../types';

interface MarketCardProps {
  market: Market;
  myPos: { yes: number; no: number };
  isActive: boolean;
  amountYes: number;
  amountNo: number;
  onSetAmount: (side: 'yes' | 'no', val: number) => void;
  onTrade: (yesDelta: number, noDelta: number) => void;
  onOpenDetail: () => void;
}

export default function MarketCard({
  market,
  myPos,
  isActive,
  amountYes,
  amountNo,
  onSetAmount,
  onTrade,
  onOpenDetail,
}: MarketCardProps) {
  const yesPrice = market.current_prices[0];
  const noPrice = market.current_prices[1];

  const handleClick = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    onOpenDetail();
  };

  if (!isActive) {
    // Past / Resolved card - simplified
    return (
      <div
        onClick={onOpenDetail}
        className="border border-zinc-700 rounded-2xl bg-zinc-900 p-5 text-white cursor-pointer hover:border-violet-500/40 hover:bg-zinc-950 transition opacity-90"
        title="Click for full history, price path at resolution, and outcome details"
      >
        <div className="font-semibold text-lg mb-1 flex items-center justify-between">
          {market.title}
          <span className="text-[10px] px-2 py-0.5 rounded bg-violet-900/40 text-violet-300 text-xs">RESOLVED</span>
        </div>
        <div className="text-xs text-zinc-400 mb-3">
          {market.id} • b={market.current_b.toFixed(1)} • resolved to {market.resolution_outcome?.toUpperCase() || '—'}
        </div>

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
  }

  // Active market card - full interactive
  return (
    <div
      onClick={onOpenDetail}
      className="border border-zinc-700 rounded-2xl bg-zinc-900 p-5 text-white cursor-pointer hover:border-emerald-500/40 hover:bg-zinc-950 transition"
      title="Click for full market view (price history time series, details, admin tools)"
    >
      <div className="font-semibold text-lg mb-1 flex items-center justify-between">
        {market.title}
        <span className="text-[10px] text-emerald-400/70 font-normal">View details →</span>
      </div>
      <div className="text-xs text-zinc-400 mb-3">{market.id} • b={market.current_b.toFixed(1)} • {market.status}</div>

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
            onClick={(e) => { e.stopPropagation(); onTrade(-myPos.yes, 0); }}
            className="flex-1 text-sm py-1.5 rounded-lg border border-emerald-400 text-emerald-200 hover:bg-emerald-900/40 active:bg-emerald-900/60 transition"
          >
            Sell All Yes ({myPos.yes})
          </button>
        )}
        {myPos.no > 0 && (
          <button
            onClick={(e) => { e.stopPropagation(); onTrade(0, -myPos.no); }}
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
              onChange={(e) => { e.stopPropagation(); onSetAmount('yes', Math.max(0, parseInt(e.target.value) || 0)); }}
              className="w-24 bg-zinc-950 border border-emerald-500/40 rounded-lg px-3 py-1.5 text-sm text-emerald-100 focus:outline-none focus:border-emerald-400"
              placeholder="shares"
            />
            <button
              onClick={(e) => { e.stopPropagation(); onTrade(amountYes, 0); }}
              disabled={amountYes === 0}
              className="flex-1 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 disabled:bg-zinc-800 disabled:text-zinc-500 text-white font-semibold text-sm rounded-lg py-1.5 transition"
            >
              Buy Yes
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onTrade(-amountYes, 0); }}
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
              onChange={(e) => { e.stopPropagation(); onSetAmount('no', Math.max(0, parseInt(e.target.value) || 0)); }}
              className="w-24 bg-zinc-950 border border-red-500/40 rounded-lg px-3 py-1.5 text-sm text-red-100 focus:outline-none focus:border-red-400"
              placeholder="shares"
            />
            <button
              onClick={(e) => { e.stopPropagation(); onTrade(0, amountNo); }}
              disabled={amountNo === 0}
              className="flex-1 bg-red-600 hover:bg-red-500 active:bg-red-700 disabled:bg-zinc-800 disabled:text-zinc-500 text-white font-semibold text-sm rounded-lg py-1.5 transition"
            >
              Buy No
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onTrade(0, -amountNo); }}
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
}
