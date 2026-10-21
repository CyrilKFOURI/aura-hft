import React, { useState, useEffect } from 'react';
import { fetchAxiLiteStatus, tuneAxiLite } from '../services/api';
import type { AxiLiteStatus } from '../types';
import { ShieldAlert, Sliders } from 'lucide-react';

export const AxiLiteLiveTuning: React.FC = () => {
  const [killSwitch, setKillSwitch] = useState<boolean>(false);
  const [skewFactor, setSkewFactor] = useState<number>(2);
  const [halfSpread, setHalfSpread] = useState<number>(100);
  const [maxInventory, setMaxInventory] = useState<number>(2000);
  const [maxOrderShares, setMaxOrderShares] = useState<number>(1000);
  const [strategyMode, setStrategyMode] = useState<string>('AVELLANEDA_STOIKOV');
  const [isApplying, setIsApplying] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    fetchAxiLiteStatus()
      .then((data: AxiLiteStatus) => {
        setKillSwitch(data.kill_switch);
        setSkewFactor(data.skew_factor);
        setHalfSpread(data.half_spread);
        setMaxInventory(data.max_inventory);
        setMaxOrderShares(data.max_order_shares);
        setStrategyMode(data.strategy_mode);
      })
      .catch(console.error);
  }, []);

  const handleApply = async (overrideKill?: boolean) => {
    setIsApplying(true);
    setFeedback(null);
    try {
      const activeKill = overrideKill !== undefined ? overrideKill : killSwitch;
      await tuneAxiLite({
        kill_switch: activeKill,
        skew_factor: skewFactor,
        half_spread: halfSpread,
        max_inventory: maxInventory,
        max_order_shares: maxOrderShares,
        strategy_mode: strategyMode,
      });
      setFeedback('AXI-Lite written in 1 cycle (3.2 ns)!');
      setTimeout(() => setFeedback(null), 3000);
    } catch (err: any) {
      setFeedback(`Error: ${err.message}`);
    } finally {
      setIsApplying(false);
    }
  };

  const toggleKillSwitch = () => {
    const nextState = !killSwitch;
    setKillSwitch(nextState);
    handleApply(nextState);
  };

  return (
    <div className={`font-mono text-xs border-b border-slate-800/80 transition-colors ${
      killSwitch ? 'bg-rose-950/20 border-rose-900/60' : ''
    }`}>
      {/* Title bar with Kill Switch */}
      <div className="bg-slate-900/60 border-b border-slate-800/80 px-3 py-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sliders className="w-3.5 h-3.5 text-amber-400" />
          <span className="font-bold text-slate-200 tracking-wide text-[11px]">
            AXI4-LITE HARDWARE TUNING
          </span>
          {feedback && (
            <span className="text-[10px] text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40 animate-fade-in">
              ✓ {feedback}
            </span>
          )}
        </div>

        {/* Emergency Kill Switch Button */}
        <button
          onClick={toggleKillSwitch}
          className={`px-3 py-1 rounded font-mono text-[11px] font-bold transition-all flex items-center gap-1.5 shadow-sm ${
            killSwitch
              ? 'bg-rose-600 text-white animate-pulse'
              : 'bg-slate-900 hover:bg-rose-950/80 text-rose-400 border border-rose-900/60'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>{killSwitch ? 'HARDWARE FREEZE ACTIVE' : 'KILL SWITCH'}</span>
        </button>
      </div>

      {/* Control Grid */}
      <div className="p-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Strategy Mode Toggle */}
        <div className="flex flex-col justify-between gap-1">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">
            Strategy Engine
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setStrategyMode('AVELLANEDA_STOIKOV')}
              className={`flex-1 py-1 px-1.5 text-[10px] font-bold rounded border transition-colors ${
                strategyMode === 'AVELLANEDA_STOIKOV'
                  ? 'bg-cyan-950/80 border-cyan-500/80 text-cyan-300'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              Avellaneda
            </button>
            <button
              onClick={() => setStrategyMode('OBI_MOMENTUM')}
              className={`flex-1 py-1 px-1.5 text-[10px] font-bold rounded border transition-colors ${
                strategyMode === 'OBI_MOMENTUM'
                  ? 'bg-purple-950/80 border-purple-500/80 text-purple-300'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              OBI Mom.
            </button>
          </div>
        </div>

        {/* Skew Factor gamma */}
        <div className="flex flex-col justify-between gap-1">
          <div className="flex justify-between text-[10px] text-slate-400">
            <span>Inventory Aversion (γ)</span>
            <span className="text-cyan-400 font-bold">{skewFactor}x</span>
          </div>
          <input
            type="range"
            min="1"
            max="10"
            step="1"
            value={skewFactor}
            onChange={(e) => setSkewFactor(Number(e.target.value))}
            className="w-full h-1.5 bg-slate-800 rounded accent-cyan-400 cursor-pointer"
          />
        </div>

        {/* Half Spread delta */}
        <div className="flex flex-col justify-between gap-1">
          <div className="flex justify-between text-[10px] text-slate-400">
            <span>Half-Spread (δ)</span>
            <span className="text-emerald-400 font-bold">${(halfSpread / 10000).toFixed(4)}</span>
          </div>
          <input
            type="range"
            min="10"
            max="500"
            step="10"
            value={halfSpread}
            onChange={(e) => setHalfSpread(Number(e.target.value))}
            className="w-full h-1.5 bg-slate-800 rounded accent-emerald-400 cursor-pointer"
          />
        </div>

        {/* Max Inventory Qmax & Apply Button */}
        <div className="flex flex-col justify-between gap-1">
          <div className="flex justify-between text-[10px] text-slate-400">
            <span>Limit (Q_max)</span>
            <span className="text-amber-400 font-bold">±{maxInventory}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <input
              type="range"
              min="500"
              max="5000"
              step="500"
              value={maxInventory}
              onChange={(e) => setMaxInventory(Number(e.target.value))}
              className="w-full h-1.5 bg-slate-800 rounded accent-amber-400 cursor-pointer"
            />
            <button
              onClick={() => handleApply()}
              disabled={isApplying}
              className="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-[10px] whitespace-nowrap transition-colors"
            >
              {isApplying ? '...' : 'APPLY'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
