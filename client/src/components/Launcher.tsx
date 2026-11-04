import React, { useState } from 'react';
import { 
  Play, ShieldAlert, AlertTriangle, 
  Check, ChevronDown, Sliders, Activity, Database
} from 'lucide-react';
import type { RunLaunchRequest, RunResponse } from '../types';
import { launchRun } from '../services/api';

const TICKERS = [
  { symbol: 'AAPL', locate: 1, name: 'Apple Inc.' },
  { symbol: 'MSFT', locate: 2, name: 'Microsoft Corp.' },
  { symbol: 'NVDA', locate: 3, name: 'NVIDIA Corp.' },
  { symbol: 'TSLA', locate: 4, name: 'Tesla Inc.' },
];

const SCENARIOS = [
  {
    id: 'balanced',
    title: 'Balanced Market (Continuous)',
    regime: 'LIQUIDITY_EQUILIBRIUM',
    depth: 'Deep 10-level BBO',
    desc: 'Continuous double auction with tight 1-2 tick spread and balanced two-sided liquidity churn.',
    ticks: 500,
  },
  {
    id: 'bullish_surge',
    title: 'Bullish Momentum Inflow',
    regime: 'BUY_IMBALANCE (+OBI)',
    depth: 'Bid Queue Dominated',
    desc: 'Heavy aggressive bid accumulation breaching positive OBI threshold to trigger immediate buy routing.',
    ticks: 500,
  },
  {
    id: 'bearish_dump',
    title: 'Bearish Liquidity Cascade',
    regime: 'SELL_IMBALANCE (-OBI)',
    depth: 'Ask Queue Dominated',
    desc: 'Rapid book depletion on bids, triggering short inventory unwinding and conservative quoting.',
    ticks: 500,
  },
  {
    id: 'risk_violation',
    title: 'Risk Stress Test (Rejection)',
    regime: 'COLLAR_BREACH',
    depth: 'Fat-Finger Anomaly',
    desc: 'Deliberately injects out-of-collar quotes and excessive lot sizes to verify 1-cycle FPGA hardware drop.',
    ticks: 300,
  },
];

interface LauncherProps {
  onRunLaunched: (run: RunResponse) => void;
}

export const Launcher: React.FC<LauncherProps> = ({ onRunLaunched }) => {
  const [selectedScenario, setSelectedScenario] = useState<string>('balanced');
  const [selectedTicker, setSelectedTicker] = useState<string>('AAPL');
  const [tickerOpen, setTickerOpen] = useState<boolean>(false);
  const [obiThreshold, setObiThreshold] = useState<number>(0.65);
  const [maxShares, setMaxShares] = useState<number>(1000);
  const [priceCollar, setPriceCollar] = useState<number>(0.05);
  const [maxNotional] = useState<number>(1000000);
  const [killSwitch, setKillSwitch] = useState<boolean>(false);
  const [tickLimit, setTickLimit] = useState<number>(500);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const activeTickerObj = TICKERS.find((t) => t.symbol === selectedTicker) || TICKERS[0];
  const activeScenarioObj = SCENARIOS.find((s) => s.id === selectedScenario) || SCENARIOS[0];

  const handleLaunch = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg(null);

    const payload: RunLaunchRequest = {
      dataset_name: `${selectedTicker}_sample_${selectedScenario}.itch`,
      symbol: selectedTicker,
      obi_threshold: obiThreshold,
      max_shares: maxShares,
      price_collar: priceCollar,
      max_notional: maxNotional,
      kill_switch: killSwitch,
      scenario: selectedScenario,
      tick_limit: tickLimit,
    };

    try {
      const run = await launchRun(payload);
      onRunLaunched(run);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Simulation launch failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-full w-full flex flex-col bg-[#07080c] text-neutral-300 font-mono select-none overflow-hidden">
      {/* Top Header Command Strip */}
      <div className="h-9 min-h-[36px] bg-[#090b10] border-b border-neutral-800/80 px-4 flex items-center justify-between text-xs">
        <div className="flex items-center space-x-2 text-neutral-400">
          <Sliders className="w-3.5 h-3.5 text-neutral-300" />
          <span className="text-neutral-100 font-semibold tracking-wide text-[11px]">
            SESSION PARAMETERIZATION
          </span>
          <span className="text-neutral-600">|</span>
          <span className="text-[10px] text-neutral-500">
            AMD KRIA KR260 HARDWARE TESTBENCH
          </span>
        </div>

        {errorMsg && (
          <div className="flex items-center space-x-1.5 text-rose-400 text-[11px]">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>{errorMsg}</span>
          </div>
        )}

        <div className="flex items-center space-x-2 text-[10px] text-neutral-500">
          <span>DATAPATH:</span>
          <span className="text-neutral-300 font-medium">49 CYCLES / 313.6ns</span>
        </div>
      </div>

      {/* Main 2-Pane Docked Grid */}
      <form onSubmit={handleLaunch} className="flex-1 grid grid-cols-1 md:grid-cols-12 overflow-hidden">
        {/* Left Pane (5 cols): Market Dataset & Scenario Matrix */}
        <div className="md:col-span-5 border-r border-neutral-800/80 flex flex-col h-full bg-[#08090d]">
          <div className="px-4 py-2 bg-[#090b10] border-b border-neutral-800/80 flex items-center justify-between">
            <span className="text-[10px] uppercase font-bold tracking-wider text-neutral-400 flex items-center space-x-1.5">
              <Database className="w-3 h-3 text-neutral-400" />
              <span>1. MARKET DATASET & ITCH 5.0 STREAM</span>
            </span>
            <span className="text-[9px] text-neutral-500">4 SCENARIOS</span>
          </div>

          {/* Ticker Dropdown Row */}
          <div className="p-3 border-b border-neutral-800/80 flex items-center justify-between">
            <span className="text-[11px] text-neutral-400">TARGET INSTRUMENT</span>
            <div className="relative">
              <button
                type="button"
                onClick={() => setTickerOpen(!tickerOpen)}
                className="flex items-center space-x-2 px-2.5 py-1 bg-neutral-900 border border-neutral-700/80 hover:border-neutral-500 text-neutral-100 text-xs transition-colors rounded-none"
              >
                <span className="font-bold">{activeTickerObj.symbol}</span>
                <span className="text-neutral-500 text-[10px]">LOC #{activeTickerObj.locate}</span>
                <ChevronDown className="w-3 h-3 text-neutral-400" />
              </button>

              {tickerOpen && (
                <div className="absolute right-0 mt-1 w-52 bg-[#0c0e14] border border-neutral-700 shadow-2xl z-50">
                  {TICKERS.map((t) => (
                    <button
                      key={t.symbol}
                      type="button"
                      onClick={() => {
                        setSelectedTicker(t.symbol);
                        setTickerOpen(false);
                      }}
                      className={`w-full px-3 py-2 text-left text-xs flex items-center justify-between border-b border-neutral-900 hover:bg-neutral-800/60 transition-colors ${
                        selectedTicker === t.symbol ? 'bg-neutral-800/80 text-white font-bold' : 'text-neutral-300'
                      }`}
                    >
                      <div>
                        <div className="font-semibold">{t.symbol}</div>
                        <div className="text-[10px] text-neutral-500">{t.name}</div>
                      </div>
                      <div className="flex items-center space-x-1.5">
                        <span className="text-[9px] text-neutral-500">LOC #{t.locate}</span>
                        {selectedTicker === t.symbol && <Check className="w-3.5 h-3.5 text-neutral-200" />}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Scenarios List (Zero cards: clean tabular items with hairline dividers) */}
          <div className="flex-1 overflow-y-auto divide-y divide-neutral-800/80">
            {SCENARIOS.map((sc) => {
              const isSelected = selectedScenario === sc.id;
              return (
                <div
                  key={sc.id}
                  onClick={() => setSelectedScenario(sc.id)}
                  className={`p-3.5 cursor-pointer transition-colors ${
                    isSelected
                      ? 'bg-neutral-900/60 border-l-2 border-l-neutral-200'
                      : 'hover:bg-neutral-900/30 text-neutral-400 border-l-2 border-l-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-semibold ${isSelected ? 'text-neutral-100' : 'text-neutral-300'}`}>
                      {sc.title}
                    </span>
                    <span className="text-[9px] font-mono px-1.5 py-0.2 bg-neutral-900 border border-neutral-800 text-neutral-400">
                      {sc.regime}
                    </span>
                  </div>
                  <p className="text-[11px] text-neutral-500 leading-relaxed mb-2">
                    {sc.desc}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-neutral-500 pt-1 border-t border-neutral-900">
                    <span>{sc.depth}</span>
                    <span className="text-neutral-400">{sc.ticks} ticks</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Active Dataset File Spec */}
          <div className="p-3 bg-[#090b10] border-t border-neutral-800/80 text-[10px] text-neutral-500 flex justify-between items-center">
            <span>BINARY FILE:</span>
            <span className="text-neutral-300 font-mono">
              {selectedTicker}_sample_{selectedScenario}.itch
            </span>
          </div>
        </div>

        {/* Right Pane (7 cols): Hardware Risk & Quantitative Parameters */}
        <div className="md:col-span-7 flex flex-col h-full bg-[#07080c]">
          <div className="px-4 py-2 bg-[#090b10] border-b border-neutral-800/80 flex items-center justify-between">
            <span className="text-[10px] uppercase font-bold tracking-wider text-neutral-400 flex items-center space-x-1.5">
              <Activity className="w-3 h-3 text-neutral-400" />
              <span>2. QUANTITATIVE THRESHOLDS & PRE-TRADE RISK</span>
            </span>
            <span className="text-[9px] text-neutral-500">1-CYCLE COMBINATIONAL</span>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {/* OBI Section */}
            <div className="space-y-2 border-b border-neutral-800/80 pb-5">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-neutral-200">
                    ORDER BOOK IMBALANCE (OBI) TRIGGER
                  </span>
                  <p className="text-[11px] text-neutral-500">
                    Fixed-point Q1.31 comparator threshold. Triggers quote front-running when exceeded.
                  </p>
                </div>
                <span className="text-sm font-bold text-neutral-100 font-mono">
                  ±{obiThreshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.20"
                max="0.95"
                step="0.05"
                value={obiThreshold}
                onChange={(e) => setObiThreshold(Number(e.target.value))}
                className="w-full accent-neutral-300 cursor-pointer h-1.5 bg-neutral-800 rounded-none"
              />
              <div className="flex justify-between text-[10px] text-neutral-600 font-mono">
                <span>±0.20 (Aggressive)</span>
                <span className="text-neutral-400">±0.65 (Institutional Default)</span>
                <span>±0.95 (Ultra-Strict)</span>
              </div>
            </div>

            {/* Simulation Ticks */}
            <div className="space-y-2 border-b border-neutral-800/80 pb-5">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-neutral-200">
                    PACKET TICKS LIMIT
                  </span>
                  <p className="text-[11px] text-neutral-500">
                    Number of ITCH L2/L3 packets to ingest through the hardware AXI-Stream parser.
                  </p>
                </div>
                <span className="text-sm font-bold text-neutral-100 font-mono">
                  {tickLimit} ticks
                </span>
              </div>
              <input
                type="range"
                min="50"
                max="1000"
                step="50"
                value={tickLimit}
                onChange={(e) => setTickLimit(Number(e.target.value))}
                className="w-full accent-neutral-300 cursor-pointer h-1.5 bg-neutral-800 rounded-none"
              />
              <div className="flex justify-between text-[10px] text-neutral-600 font-mono">
                <span>50 (Quick Verification)</span>
                <span className="text-neutral-400">500 (Standard Sample)</span>
                <span>1,000 (Stress Window)</span>
              </div>
            </div>

            {/* Pre-trade Max Shares & Collar Deviation */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 border-b border-neutral-800/80 pb-5">
              <div className="space-y-2">
                <span className="text-[11px] font-semibold text-neutral-300">
                  MAX ORDER VOLUME (SHARES)
                </span>
                <input
                  type="number"
                  min="10"
                  max="10000"
                  step="50"
                  value={maxShares}
                  onChange={(e) => setMaxShares(Number(e.target.value))}
                  className="w-full bg-[#0a0c12] border border-neutral-800 focus:border-neutral-500 px-3 py-1.5 text-xs text-neutral-100 font-mono rounded-none outline-none"
                />
                <span className="text-[10px] text-neutral-600 block">
                  Fat-finger protection ceiling
                </span>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-[11px] font-semibold text-neutral-300">
                    PRICE COLLAR DEVIATION
                  </span>
                  <span className="text-xs font-bold text-neutral-100 font-mono">
                    {(priceCollar * 100).toFixed(1)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.01"
                  max="0.20"
                  step="0.01"
                  value={priceCollar}
                  onChange={(e) => setPriceCollar(Number(e.target.value))}
                  className="w-full accent-neutral-300 cursor-pointer h-1.5 bg-neutral-800 rounded-none"
                />
                <span className="text-[10px] text-neutral-600 block">
                  BBO deviation boundary (max spread slippage)
                </span>
              </div>
            </div>

            {/* Hardware Kill Switch */}
            <div className="p-3 bg-neutral-900/30 border border-neutral-800 flex items-center justify-between">
              <div className="space-y-0.5">
                <div className="flex items-center space-x-1.5 text-xs font-bold text-neutral-200">
                  <ShieldAlert className={`w-3.5 h-3.5 ${killSwitch ? 'text-rose-400' : 'text-neutral-500'}`} />
                  <span>EMERGENCY TRANSMITTER LOCK (KILL SWITCH)</span>
                </div>
                <p className="text-[10px] text-neutral-500">
                  Instantly asserts hardware drop on all generated OUCH 5.0 outbound frames.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setKillSwitch(!killSwitch)}
                className={`px-3 py-1 text-xs font-bold font-mono transition-colors border ${
                  killSwitch
                    ? 'bg-rose-950/60 border-rose-700 text-rose-300'
                    : 'bg-neutral-800/50 border-neutral-700 text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {killSwitch ? 'LOCKED (ACTIVE)' : 'DISABLED'}
              </button>
            </div>
          </div>

          {/* Bottom Execution Action Bar */}
          <div className="h-12 min-h-[48px] bg-[#090b10] border-t border-neutral-800/80 px-4 flex items-center justify-between">
            <div className="text-[11px] text-neutral-500 flex items-center space-x-2">
              <span>TARGET:</span>
              <span className="text-neutral-300 font-bold">{selectedTicker}</span>
              <span className="text-neutral-700">·</span>
              <span>SCENARIO:</span>
              <span className="text-neutral-300 font-bold">{activeScenarioObj.title}</span>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="px-5 py-1.5 bg-neutral-100 hover:bg-white text-neutral-950 font-bold text-xs flex items-center space-x-2 transition-all disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isLoading ? 'EXECUTING PIPELINE...' : 'DISPATCH SIMULATION RUN'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
