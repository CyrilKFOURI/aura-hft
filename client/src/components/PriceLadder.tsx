import React from 'react';
import type { TickData } from '../types';

interface PriceLadderProps {
  tick: TickData | null;
}

export const PriceLadder: React.FC<PriceLadderProps> = ({ tick }) => {
  if (!tick) {
    return (
      <div className="p-8 flex flex-col items-center justify-center min-h-[220px] text-slate-500 font-mono text-xs">
        <p>AWAITING MARKET FEED DATA...</p>
      </div>
    );
  }

  const bids = tick.top_5?.bids || [[tick.best_bid, tick.bid_qty_l1]];
  const asks = tick.top_5?.asks || [[tick.best_ask, tick.ask_qty_l1]];

  const maxVolume = Math.max(
    ...bids.map((b) => b[1]),
    ...asks.map((a) => a[1]),
    1000
  );

  const spread = Math.max(0, Number((tick.best_ask - tick.best_bid).toFixed(4)));
  const spreadTicks = Math.round(spread * 100);

  return (
    <div className="font-mono">
      {/* Sub-header inside the unified panel */}
      <div className="bg-slate-900/60 border-b border-slate-800/80 px-3 py-2 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-bold text-slate-200 tracking-wide text-[11px]">L2 MARKET DEPTH</span>
          <span className="bg-slate-800/80 text-slate-400 px-1 py-0.2 rounded text-[9px] border border-slate-700/50">
            TOP-5 BBO
          </span>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="text-slate-400">SPREAD</span>
          <span className="text-cyan-400 font-bold">${spread.toFixed(2)}</span>
          <span className="text-slate-500 text-[10px]">({spreadTicks}t)</span>
        </div>
      </div>

      {/* Main Dual-Sided Ladder */}
      <div className="grid grid-cols-2 divide-x divide-slate-800/80 p-2.5 gap-y-1">
        {/* BIDS SIDE */}
        <div className="pr-1.5">
          <div className="flex justify-between text-[10px] text-slate-400 pb-1 border-b border-slate-800/60 mb-1 px-1">
            <span>VOLUME</span>
            <span>BID</span>
          </div>

          <div className="space-y-0.5">
            {bids.map(([price, vol], idx) => {
              const pct = Math.min(100, Math.round((vol / maxVolume) * 100));
              const isBBO = idx === 0;

              return (
                <div
                  key={`bid-${price}-${idx}`}
                  className={`relative flex items-center justify-between px-2 py-1 rounded text-[11px] overflow-hidden transition-all ${
                    isBBO ? 'bg-emerald-950/40 border border-emerald-800/50' : 'hover:bg-slate-800/30'
                  }`}
                >
                  <div
                    className="absolute inset-y-0 right-0 bg-emerald-500/10 pointer-events-none transition-all duration-150"
                    style={{ width: `${pct}%` }}
                  />
                  <div className="relative z-10 flex items-center gap-1.5 text-slate-300">
                    <span className="text-slate-500 text-[9px] w-2">{idx + 1}</span>
                    <span className="font-medium">{vol.toLocaleString()}</span>
                  </div>
                  <div className="relative z-10 font-bold text-emerald-400">
                    ${price.toFixed(2)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ASKS SIDE */}
        <div className="pl-1.5">
          <div className="flex justify-between text-[10px] text-slate-400 pb-1 border-b border-slate-800/60 mb-1 px-1">
            <span>ASK</span>
            <span>VOLUME</span>
          </div>

          <div className="space-y-0.5">
            {asks.map(([price, vol], idx) => {
              const pct = Math.min(100, Math.round((vol / maxVolume) * 100));
              const isBBO = idx === 0;

              return (
                <div
                  key={`ask-${price}-${idx}`}
                  className={`relative flex items-center justify-between px-2 py-1 rounded text-[11px] overflow-hidden transition-all ${
                    isBBO ? 'bg-rose-950/40 border border-rose-800/50' : 'hover:bg-slate-800/30'
                  }`}
                >
                  <div
                    className="absolute inset-y-0 left-0 bg-rose-500/10 pointer-events-none transition-all duration-150"
                    style={{ width: `${pct}%` }}
                  />
                  <div className="relative z-10 font-bold text-rose-400">
                    ${price.toFixed(2)}
                  </div>
                  <div className="relative z-10 flex items-center gap-1.5 text-slate-300">
                    <span className="font-medium">{vol.toLocaleString()}</span>
                    <span className="text-slate-500 text-[9px] w-2 text-right">{idx + 1}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
