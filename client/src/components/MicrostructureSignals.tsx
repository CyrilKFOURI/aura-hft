import React from 'react';
import type { TickData } from '../types';
import { Gauge, ArrowUpRight, ArrowDownRight, Layers, Target } from 'lucide-react';

interface MicrostructureSignalsProps {
  tick: TickData | null;
  obiThreshold: number;
}

export const MicrostructureSignals: React.FC<MicrostructureSignalsProps> = ({
  tick,
  obiThreshold,
}) => {
  if (!tick) {
    return (
      <div className="p-4 text-center text-xs text-slate-500 font-mono">
        WAITING FOR MICROSTRUCTURE FEED...
      </div>
    );
  }

  const obi = tick.obi_value;
  const isTriggered = Math.abs(obi) >= obiThreshold;
  const midPrice = (tick.best_bid + tick.best_ask) / 2.0;
  const microDelta = tick.micro_price - midPrice;
  const queuePos = tick.queue_pos !== null ? tick.queue_pos : 0;
  const isTopQueue = queuePos === 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-800/80 font-mono text-xs">
      {/* 1. OBI METRIC */}
      <div className="p-3 flex flex-col justify-between gap-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Gauge className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-semibold text-slate-200 text-[11px]">OBI IMBALANCE</span>
          </div>
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${
              isTriggered
                ? obi > 0
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-700/60'
                  : 'bg-rose-950 text-rose-400 border border-rose-700/60'
                : 'bg-slate-800/60 text-slate-400'
            }`}
          >
            {isTriggered ? (obi > 0 ? 'BUY' : 'SELL') : 'NEUTRAL'}
          </span>
        </div>

        <div className="flex items-baseline justify-between">
          <span
            className={`text-lg font-bold tracking-tight ${
              obi > 0 ? 'text-emerald-400' : obi < 0 ? 'text-rose-400' : 'text-slate-300'
            }`}
          >
            {obi >= 0 ? `+${obi.toFixed(4)}` : obi.toFixed(4)}
          </span>
          <span className="text-[10px] text-slate-500">
            Thr: ±{obiThreshold.toFixed(2)}
          </span>
        </div>

        {/* Minimalist Gauge Bar */}
        <div className="w-full h-1.5 bg-slate-900 border border-slate-800 rounded-full overflow-hidden relative">
          <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-slate-600 z-10" />
          <div
            className={`h-full transition-all duration-150 ${
              obi >= 0 ? 'bg-emerald-500' : 'bg-rose-500'
            }`}
            style={{
              width: `${Math.abs(obi * 50)}%`,
              marginLeft: obi >= 0 ? '50%' : `${50 - Math.abs(obi * 50)}%`,
            }}
          />
        </div>
      </div>

      {/* 2. MICRO-PRICE */}
      <div className="p-3 flex flex-col justify-between gap-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Target className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-semibold text-slate-200 text-[11px]">MICRO-PRICE</span>
          </div>
          <span className="text-[9px] text-slate-400 bg-slate-800/60 px-1.5 py-0.5 rounded">
            EL KAROUI
          </span>
        </div>

        <div className="flex items-baseline justify-between">
          <span className="text-lg font-bold text-cyan-300">
            ${tick.micro_price.toFixed(4)}
          </span>
          <span
            className={`text-[11px] font-semibold flex items-center ${
              microDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {microDelta >= 0 ? (
              <ArrowUpRight className="w-3 h-3 mr-0.5" />
            ) : (
              <ArrowDownRight className="w-3 h-3 mr-0.5" />
            )}
            {microDelta >= 0 ? '+' : ''}
            {(microDelta * 100).toFixed(2)}¢
          </span>
        </div>

        <div className="flex justify-between text-[10px] text-slate-400 pt-0.5">
          <span>Mid: ${midPrice.toFixed(4)}</span>
          <span>Spread: ${(tick.best_ask - tick.best_bid).toFixed(2)}</span>
        </div>
      </div>

      {/* 3. QUEUE TRACKER */}
      <div className="p-3 flex flex-col justify-between gap-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Layers className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-semibold text-slate-200 text-[11px]">QUEUE TRACKER</span>
          </div>
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${
              isTopQueue
                ? 'bg-emerald-950 text-emerald-400 border border-emerald-600/60'
                : 'bg-slate-800/60 text-slate-400'
            }`}
          >
            {isTopQueue ? 'TOP QUEUE' : 'IN QUEUE'}
          </span>
        </div>

        <div className="flex items-baseline justify-between">
          <span className="text-lg font-bold text-white">
            {queuePos.toLocaleString()}
          </span>
          <span className="text-[10px] text-slate-500">shares ahead</span>
        </div>

        <div className="w-full h-1.5 bg-slate-900 border border-slate-800 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-200 ${
              isTopQueue ? 'bg-emerald-400' : 'bg-cyan-500'
            }`}
            style={{
              width: isTopQueue ? '100%' : `${Math.max(5, 100 - (queuePos / 2000) * 100)}%`,
            }}
          />
        </div>
      </div>
    </div>
  );
};
