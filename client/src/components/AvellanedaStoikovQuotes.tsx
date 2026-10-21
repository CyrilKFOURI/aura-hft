import React from 'react';
import type { TickData } from '../types';

interface AvellanedaStoikovQuotesProps {
  tick: TickData | null;
  skewFactor?: number;
  halfSpread?: number;
  inventory?: number;
  maxInventory?: number;
}

export const AvellanedaStoikovQuotes: React.FC<AvellanedaStoikovQuotesProps> = ({
  tick,
  skewFactor = 2,
  halfSpread = 100, // in raw cents (0.0100)
  inventory = 150,
  maxInventory = 2000,
}) => {
  const midPrice = tick
    ? (tick.best_bid + tick.best_ask) / 2
    : 150.05;

  const skewDollar = (inventory * skewFactor) / 10000;
  const reservationPrice = midPrice - skewDollar;

  const halfSpreadDollar = halfSpread / 10000;
  const optimalBid = reservationPrice - halfSpreadDollar;
  const optimalAsk = reservationPrice + halfSpreadDollar;

  const invPct = Math.min(Math.max((inventory / maxInventory) * 100, -100), 100);

  return (
    <div className="font-mono text-xs">
      {/* Title bar */}
      <div className="bg-slate-900/60 border-b border-slate-800/80 px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span className="font-bold text-slate-200 tracking-wide text-[11px]">
            AVELLANEDA-STOIKOV QUANT ENGINE
          </span>
        </div>
        <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-950/60 border border-cyan-800/60 text-cyan-300">
          3-Cycle DSP (312.5 MHz)
        </span>
      </div>

      {/* Grid of Key Prices without bulky cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-slate-800/80 border-b border-slate-800/80">
        {/* Market Mid */}
        <div className="p-2.5">
          <div className="text-[10px] text-slate-400 uppercase tracking-wider">
            Mid-Price (S)
          </div>
          <div className="text-base font-bold text-slate-100 mt-0.5">
            ${midPrice.toFixed(4)}
          </div>
        </div>

        {/* Reservation Price */}
        <div className="p-2.5">
          <div className="text-[10px] text-cyan-400 uppercase tracking-wider flex items-center justify-between">
            <span>Reservation r(s,q)</span>
            {inventory !== 0 && (
              <span className={`text-[9px] ${inventory > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                {inventory > 0 ? '↓ Long Skew' : '↑ Short Skew'}
              </span>
            )}
          </div>
          <div className="text-base font-bold text-cyan-300 mt-0.5">
            ${reservationPrice.toFixed(4)}
          </div>
        </div>

        {/* Optimal Bid */}
        <div className="p-2.5">
          <div className="text-[10px] text-emerald-400 uppercase tracking-wider">
            Optimal Bid (r - δ)
          </div>
          <div className="text-base font-bold text-emerald-400 mt-0.5">
            ${optimalBid.toFixed(4)}
          </div>
        </div>

        {/* Optimal Ask */}
        <div className="p-2.5">
          <div className="text-[10px] text-rose-400 uppercase tracking-wider">
            Optimal Ask (r + δ)
          </div>
          <div className="text-base font-bold text-rose-400 mt-0.5">
            ${optimalAsk.toFixed(4)}
          </div>
        </div>
      </div>

      {/* Inventory Gauge bar */}
      <div className="p-2.5 bg-slate-900/20">
        <div className="flex items-center justify-between text-[11px] mb-1">
          <span className="text-slate-400">Inventory Tracker (q):</span>
          <span className="font-bold text-slate-200">
            {inventory > 0 ? `+${inventory}` : inventory} / ±{maxInventory} shares
          </span>
        </div>

        <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex relative">
          <div className="w-1/2 flex justify-end">
            {invPct < 0 && (
              <div
                className="h-full bg-rose-500 rounded-l-full transition-all duration-300"
                style={{ width: `${Math.abs(invPct)}%` }}
              />
            )}
          </div>
          <div className="w-0.5 h-full bg-slate-600 z-10" />
          <div className="w-1/2 flex justify-start">
            {invPct > 0 && (
              <div
                className="h-full bg-emerald-500 rounded-r-full transition-all duration-300"
                style={{ width: `${invPct}%` }}
              />
            )}
          </div>
        </div>
        <div className="flex justify-between text-[9px] text-slate-500 mt-1">
          <span>Short (-{maxInventory})</span>
          <span>Flat (0)</span>
          <span>Long (+{maxInventory})</span>
        </div>
      </div>
    </div>
  );
};
