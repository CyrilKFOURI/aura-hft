import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, Pause, SkipBack, SkipForward, RotateCcw, 
  ChevronDown, Check, Zap, ShieldAlert
} from 'lucide-react';
import type { TickData, OrderData, ReplayStatus, AxiLiteStatus } from '../types';
import { fetchAxiLiteStatus, tuneAxiLite } from '../services/api';

const TICKERS = [
  { symbol: 'AAPL', locate: 1, name: 'Apple Inc.', color: 'text-neutral-100' },
  { symbol: 'MSFT', locate: 2, name: 'Microsoft Corp.', color: 'text-neutral-100' },
  { symbol: 'NVDA', locate: 3, name: 'NVIDIA Corp.', color: 'text-neutral-100' },
  { symbol: 'TSLA', locate: 4, name: 'Tesla Inc.', color: 'text-neutral-100' },
];

interface TerminalWorkspaceProps {
  status: ReplayStatus;
  tick: TickData | null;
  orders: OrderData[];
  lastOrder: OrderData | null;
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
  play: (speed?: number) => void;
  pause: () => void;
  step: (dir: number) => void;
  seek: (index: number) => void;
  setSpeed: (speed: number) => void;
  obiThreshold?: number;
}

export const TerminalWorkspace: React.FC<TerminalWorkspaceProps> = ({
  status,
  tick,
  orders,
  lastOrder,
  selectedTicker,
  onSelectTicker,
  play,
  pause,
  step,
  seek,
  setSpeed,
  obiThreshold = 0.65,
}) => {
  // Ticker dropdown state
  const [tickerOpen, setTickerOpen] = useState(false);
  const tickerRef = useRef<HTMLDivElement>(null);
  const activeTicker = TICKERS.find((t) => t.symbol === selectedTicker) || TICKERS[0];

  // AXI-Lite tuning state
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

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (tickerRef.current && !tickerRef.current.contains(e.target as Node)) {
        setTickerOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleApplyAxi = async (overrideKill?: boolean) => {
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
      setFeedback('REG WRITTEN (3.2ns)');
      setTimeout(() => setFeedback(null), 3000);
    } catch (err: any) {
      setFeedback(`ERR: ${err.message}`);
    } finally {
      setIsApplying(false);
    }
  };

  const toggleKillSwitch = () => {
    const next = !killSwitch;
    setKillSwitch(next);
    handleApplyAxi(next);
  };

  // Calculations for Order Book & Depth
  const bids = tick?.top_5?.bids || (tick ? [[tick.best_bid, tick.bid_qty_l1]] : [[150.00, 500]]);
  const asks = tick?.top_5?.asks || (tick ? [[tick.best_ask, tick.ask_qty_l1]] : [[150.02, 500]]);
  const maxVolume = Math.max(
    ...bids.map((b) => b[1]),
    ...asks.map((a) => a[1]),
    1000
  );
  const bestBid = tick ? tick.best_bid : 150.00;
  const bestAsk = tick ? tick.best_ask : 150.02;
  const spread = Math.max(0, Number((bestAsk - bestBid).toFixed(4)));
  const spreadTicks = Math.round(spread * 100);
  const midPrice = (bestBid + bestAsk) / 2.0;

  // Quantitative Microstructure
  const obi = tick ? tick.obi_value : 0;
  const isObiTriggered = Math.abs(obi) >= obiThreshold;
  const microPrice = tick ? tick.micro_price : midPrice;
  const microDelta = microPrice - midPrice;
  const queuePos = tick?.queue_pos ?? 0;
  const isTopQueue = queuePos === 0;

  // Avellaneda-Stoikov Model
  const inventory = 150;
  const skewDollar = (inventory * skewFactor) / 10000;
  const reservationPrice = midPrice - skewDollar;
  const halfSpreadDollar = halfSpread / 10000;
  const optimalBid = reservationPrice - halfSpreadDollar;
  const optimalAsk = reservationPrice + halfSpreadDollar;
  const invPct = Math.min(Math.max((inventory / maxInventory) * 100, -100), 100);

  const isPlaying = status.state === 'PLAYING';
  const speeds = [0.5, 1.0, 2.0, 5.0, 10.0];

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] w-full bg-[#05070b] text-neutral-300 font-mono text-[11px] select-none border border-neutral-800/80">
      
      {/* =================================================================== */}
      {/* 1. TOP DOCKED COMMAND STRIP (NO FLOATING BUBBLES)                   */}
      {/* =================================================================== */}
      <div className="h-10 bg-[#090c13] border-b border-neutral-800/80 px-3 flex items-center justify-between gap-3 text-xs shrink-0">
        
        {/* Left: Ticker Dropdown & Transport Controls */}
        <div className="flex items-center gap-3">
          {/* Flat Minimalist Ticker Dropdown */}
          <div className="relative" ref={tickerRef}>
            <button
              onClick={() => setTickerOpen(!tickerOpen)}
              className="flex items-center gap-2 px-2.5 py-1 bg-neutral-900/90 hover:bg-neutral-800/80 border border-neutral-700/60 rounded-none text-xs transition-colors"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span className="font-bold text-white tracking-wider">{activeTicker.symbol}</span>
              <span className="text-neutral-500 text-[10px] hidden sm:inline">{activeTicker.name}</span>
              <span className="text-[9px] text-neutral-400 bg-neutral-800 px-1 py-0.2">
                #{activeTicker.locate}
              </span>
              <ChevronDown className={`w-3 h-3 text-neutral-400 transition-transform ${tickerOpen ? 'rotate-180' : ''}`} />
            </button>

            {tickerOpen && (
              <div className="absolute left-0 mt-1 w-56 bg-[#0a0d16] border border-neutral-700 shadow-2xl z-50 divide-y divide-neutral-800">
                <div className="px-2.5 py-1 text-[9px] uppercase tracking-wider text-neutral-500 bg-neutral-950">
                  Select Active Ticker
                </div>
                <div className="py-0.5">
                  {TICKERS.map((t) => {
                    const isSel = t.symbol === selectedTicker;
                    return (
                      <button
                        key={t.symbol}
                        onClick={() => {
                          onSelectTicker(t.symbol);
                          setTickerOpen(false);
                        }}
                        className={`w-full px-2.5 py-1.5 text-left flex items-center justify-between text-xs hover:bg-neutral-800/60 transition-colors ${
                          isSel ? 'bg-neutral-800/40 text-white' : 'text-neutral-400'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`font-bold ${t.color}`}>{t.symbol}</span>
                          <span className="text-[10px] text-neutral-500">{t.name}</span>
                        </div>
                        {isSel && <Check className="w-3 h-3 text-emerald-400" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="h-4 w-[1px] bg-neutral-800" />

          {/* Transport buttons */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => (isPlaying ? pause() : play(status.speed))}
              className={`flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold transition-colors ${
                isPlaying
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30'
                  : 'bg-neutral-100 text-neutral-950 hover:bg-white'
              }`}
            >
              {isPlaying ? <Pause className="w-3 h-3 fill-current" /> : <Play className="w-3 h-3 fill-current" />}
              <span>{isPlaying ? 'PAUSE' : 'PLAY'}</span>
            </button>

            <button
              onClick={() => step(-1)}
              disabled={status.current_index <= 0}
              className="p-1 bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-white hover:bg-neutral-800 disabled:opacity-30"
              title="Step -1"
            >
              <SkipBack className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => step(1)}
              disabled={status.current_index >= status.total_ticks - 1}
              className="p-1 bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-white hover:bg-neutral-800 disabled:opacity-30"
              title="Step +1"
            >
              <SkipForward className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => seek(0)}
              className="p-1 bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-white hover:bg-neutral-800"
              title="Rewind"
            >
              <RotateCcw className="w-3 h-3" />
            </button>
          </div>

          {/* Speeds */}
          <div className="flex items-center bg-neutral-900 border border-neutral-800">
            {speeds.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setSpeed(s);
                  if (isPlaying) play(s);
                }}
                className={`px-1.5 py-0.5 text-[10px] font-bold ${
                  status.speed === s
                    ? 'bg-neutral-800 text-neutral-100 border-r border-neutral-700 last:border-r-0'
                    : 'text-neutral-500 hover:text-neutral-300 border-r border-neutral-800/40 last:border-r-0'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>

        {/* Center: Inline Timeline Scrubber */}
        <div className="flex-1 max-w-md hidden md:flex items-center gap-2">
          <input
            type="range"
            min={0}
            max={Math.max(0, status.total_ticks - 1)}
            value={status.current_index}
            onChange={(e) => seek(Number(e.target.value))}
            className="w-full h-1 bg-neutral-800 appearance-none cursor-pointer accent-neutral-300 focus:outline-none"
          />
          <span className="text-[10px] text-neutral-500 shrink-0 tabular-nums">
            {status.current_index + 1}/{status.total_ticks} ({status.progress_pct.toFixed(0)}%)
          </span>
        </div>

        {/* Right: Quick Kill Switch Button & Hardware Status */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleKillSwitch}
            className={`px-2.5 py-1 text-[10px] font-bold flex items-center gap-1.5 transition-colors ${
              killSwitch
                ? 'bg-rose-600 text-white animate-pulse'
                : 'bg-neutral-900 hover:bg-rose-950/60 text-rose-400 border border-rose-900/60'
            }`}
          >
            <ShieldAlert className="w-3 h-3" />
            <span>{killSwitch ? 'HARDWARE FREEZE' : 'KILL SWITCH'}</span>
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* 2. MAIN WORKBENCH: ZERO-CARD CONTINUOUS MULTI-PANE SURFACE          */}
      {/* =================================================================== */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 overflow-hidden divide-y lg:divide-y-0 lg:divide-x divide-neutral-800/80">
        
        {/* ================================================================= */}
        {/* PANE 1 (LEFT, 4 COLS): L2 ORDER BOOK & MICROSTRUCTURE             */}
        {/* ================================================================= */}
        <div className="lg:col-span-4 flex flex-col h-full bg-[#080a10] divide-y divide-neutral-800/80 overflow-y-auto">
          
          {/* L2 Depth Sub-pane */}
          <div className="flex flex-col">
            <div className="h-7 px-3 bg-[#0c0f17] border-b border-neutral-800/80 flex items-center justify-between text-[10px] font-bold text-neutral-400">
              <span className="tracking-wider uppercase">L2 LIMIT ORDER BOOK</span>
              <div className="flex items-center gap-2 text-neutral-400">
                <span>SPREAD:</span>
                <span className="text-neutral-100 font-bold">${spread.toFixed(2)}</span>
                <span className="text-neutral-500">({spreadTicks}t)</span>
              </div>
            </div>

            {/* Asks Table (Upper Book - inverted order so lowest ask is closest to spread) */}
            <div className="p-2 space-y-0.5">
              <div className="flex justify-between text-[9px] text-neutral-500 px-1 pb-0.5 border-b border-neutral-800/60 uppercase">
                <span>Ask Depth</span>
                <span>Ask Price</span>
                <span>Level</span>
              </div>
              {[...asks].reverse().map(([price, vol], idx) => {
                const pct = Math.min(100, Math.round((vol / maxVolume) * 100));
                const levelNum = asks.length - idx;
                const isBBO = levelNum === 1;

                return (
                  <div
                    key={`ask-${price}-${idx}`}
                    className={`relative flex items-center justify-between px-2 py-0.5 text-[11px] overflow-hidden ${
                      isBBO ? 'bg-rose-950/30 border-l-2 border-rose-500' : 'hover:bg-neutral-800/30'
                    }`}
                  >
                    <div
                      className="absolute inset-y-0 left-0 bg-rose-500/10 pointer-events-none"
                      style={{ width: `${pct}%` }}
                    />
                    <span className="relative z-10 text-neutral-300 font-mono tabular-nums">{vol.toLocaleString()}</span>
                    <span className="relative z-10 font-bold text-rose-400 tabular-nums">${price.toFixed(2)}</span>
                    <span className="relative z-10 text-[9px] text-neutral-600">A{levelNum}</span>
                  </div>
                );
              })}
            </div>

            {/* Mid-Market Price Line */}
            <div className="h-6 bg-neutral-900/80 border-y border-neutral-800/80 px-3 flex items-center justify-between text-[10px]">
              <span className="text-neutral-500 font-bold">MARKET MID</span>
              <span className="font-bold text-white text-xs tabular-nums">${midPrice.toFixed(4)}</span>
              <span className="text-neutral-500">BBO TOP-5</span>
            </div>

            {/* Bids Table (Lower Book) */}
            <div className="p-2 space-y-0.5">
              <div className="flex justify-between text-[9px] text-neutral-500 px-1 pb-0.5 border-b border-neutral-800/60 uppercase">
                <span>Bid Depth</span>
                <span>Bid Price</span>
                <span>Level</span>
              </div>
              {bids.map(([price, vol], idx) => {
                const pct = Math.min(100, Math.round((vol / maxVolume) * 100));
                const isBBO = idx === 0;

                return (
                  <div
                    key={`bid-${price}-${idx}`}
                    className={`relative flex items-center justify-between px-2 py-0.5 text-[11px] overflow-hidden ${
                      isBBO ? 'bg-emerald-950/30 border-l-2 border-emerald-500' : 'hover:bg-neutral-800/30'
                    }`}
                  >
                    <div
                      className="absolute inset-y-0 left-0 bg-emerald-500/10 pointer-events-none"
                      style={{ width: `${pct}%` }}
                    />
                    <span className="relative z-10 text-neutral-300 font-mono tabular-nums">{vol.toLocaleString()}</span>
                    <span className="relative z-10 font-bold text-emerald-400 tabular-nums">${price.toFixed(2)}</span>
                    <span className="relative z-10 text-[9px] text-neutral-600">B{idx + 1}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Microstructure Metrics Sub-pane */}
          <div className="flex flex-col">
            <div className="h-7 px-3 bg-[#0c0f17] border-b border-neutral-800/80 flex items-center justify-between text-[10px] font-bold text-neutral-400">
              <span className="tracking-wider uppercase">MICROSTRUCTURE & SIGNALS</span>
              <span className="text-neutral-500 text-[9px]">II=1 PIPELINED</span>
            </div>

            <div className="p-3 space-y-2.5">
              {/* OBI Row */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-neutral-400 text-[10px] uppercase">OBI Imbalance (Q1.31)</span>
                  <span
                    className={`text-[9px] font-bold px-1.5 py-0.2 rounded-none ${
                      isObiTriggered
                        ? obi > 0
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/60'
                          : 'bg-rose-950 text-rose-300 border border-rose-700/60'
                        : 'bg-neutral-800 text-neutral-400'
                    }`}
                  >
                    {isObiTriggered ? (obi > 0 ? '+BUY SIGNAL' : '-SELL SIGNAL') : 'NEUTRAL'}
                  </span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className={`text-base font-bold tabular-nums ${obi > 0 ? 'text-emerald-400' : obi < 0 ? 'text-rose-400' : 'text-neutral-300'}`}>
                    {obi >= 0 ? `+${obi.toFixed(4)}` : obi.toFixed(4)}
                  </span>
                  <span className="text-[10px] text-neutral-500">Limit: ±{obiThreshold.toFixed(2)}</span>
                </div>
                {/* Minimalist Gauge Bar */}
                <div className="w-full h-1.5 bg-neutral-900 border border-neutral-800 relative">
                  <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-neutral-600 z-10" />
                  <div
                    className={`h-full transition-all duration-150 ${obi >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`}
                    style={{
                      width: `${Math.abs(obi * 50)}%`,
                      marginLeft: obi >= 0 ? '50%' : `${50 - Math.abs(obi * 50)}%`,
                    }}
                  />
                </div>
              </div>

              {/* Micro-Price & Delta */}
              <div className="pt-2 border-t border-neutral-800/60 flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-neutral-500 uppercase">Micro-Price (El Karoui)</div>
                  <div className="text-sm font-bold text-neutral-100 tabular-nums">${microPrice.toFixed(4)}</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-neutral-500 uppercase">Delta vs Mid</div>
                  <div className={`text-xs font-bold tabular-nums flex items-center justify-end ${microDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {microDelta >= 0 ? '+' : ''}{(microDelta * 100).toFixed(2)}¢
                  </div>
                </div>
              </div>

              {/* Queue Position */}
              <div className="pt-2 border-t border-neutral-800/60 flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-neutral-500 uppercase">Queue Tracker</div>
                  <div className="text-xs font-bold text-neutral-200 tabular-nums">{queuePos.toLocaleString()} sh ahead</div>
                </div>
                <span className={`text-[9px] px-1.5 py-0.2 font-bold ${isTopQueue ? 'text-emerald-400 bg-emerald-950/60' : 'text-neutral-400 bg-neutral-900'}`}>
                  {isTopQueue ? 'TOP OF QUEUE' : 'WAITING'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* ================================================================= */}
        {/* PANE 2 (MIDDLE, 4 COLS): QUANT ENGINE & AXI4-LITE TUNING          */}
        {/* ================================================================= */}
        <div className="lg:col-span-4 flex flex-col h-full bg-[#07090f] divide-y divide-neutral-800/80 overflow-y-auto">
          
          {/* Avellaneda-Stoikov Model */}
          <div className="flex flex-col">
            <div className="h-7 px-3 bg-[#0c0f17] border-b border-neutral-800/80 flex items-center justify-between text-[10px] font-bold text-neutral-400">
              <span className="tracking-wider uppercase">AVELLANEDA-STOIKOV QUANT MODEL</span>
              <span className="text-[9px] text-neutral-500">DSP48E2</span>
            </div>

            <div className="p-3 space-y-3">
              {/* 4 Core Metrics in clean linear row */}
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2 bg-neutral-900/60 border border-neutral-800/80">
                  <div className="text-[9px] text-neutral-500 uppercase">Market Mid (S)</div>
                  <div className="text-sm font-bold text-neutral-200 tabular-nums mt-0.5">${midPrice.toFixed(4)}</div>
                </div>

                <div className="p-2 bg-neutral-900/60 border border-neutral-800/80">
                  <div className="text-[9px] text-neutral-400 uppercase flex items-center justify-between">
                    <span>Reservation r(s,q)</span>
                    <span className="text-[8px] text-neutral-500">{inventory > 0 ? '↓ Long' : '↑ Short'}</span>
                  </div>
                  <div className="text-sm font-bold text-neutral-100 tabular-nums mt-0.5">${reservationPrice.toFixed(4)}</div>
                </div>

                <div className="p-2 bg-neutral-900/60 border border-neutral-800/80">
                  <div className="text-[9px] text-neutral-400 uppercase">Optimal Bid (r - δ)</div>
                  <div className="text-sm font-bold text-emerald-400 tabular-nums mt-0.5">${optimalBid.toFixed(4)}</div>
                </div>

                <div className="p-2 bg-neutral-900/60 border border-neutral-800/80">
                  <div className="text-[9px] text-neutral-400 uppercase">Optimal Ask (r + δ)</div>
                  <div className="text-sm font-bold text-rose-400 tabular-nums mt-0.5">${optimalAsk.toFixed(4)}</div>
                </div>
              </div>

              {/* Inventory Meter */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-neutral-400">Inventory Exposure (q):</span>
                  <span className="font-bold text-neutral-200 tabular-nums">{inventory > 0 ? `+${inventory}` : inventory} / ±{maxInventory} shares</span>
                </div>
                <div className="h-1.5 w-full bg-neutral-900 border border-neutral-800 flex relative">
                  <div className="w-1/2 flex justify-end">
                    {invPct < 0 && (
                      <div className="h-full bg-rose-500" style={{ width: `${Math.abs(invPct)}%` }} />
                    )}
                  </div>
                  <div className="w-0.5 h-full bg-neutral-600 z-10" />
                  <div className="w-1/2 flex justify-start">
                    {invPct > 0 && (
                      <div className="h-full bg-emerald-500" style={{ width: `${invPct}%` }} />
                    )}
                  </div>
                </div>
                <div className="flex justify-between text-[8px] text-neutral-500">
                  <span>Short (-{maxInventory})</span>
                  <span>Flat (0)</span>
                  <span>Long (+{maxInventory})</span>
                </div>
              </div>
            </div>
          </div>

          {/* AXI4-Lite Register Tuning Sub-pane */}
          <div className="flex flex-col flex-1">
            <div className="h-7 px-3 bg-[#0c0f17] border-b border-neutral-800/80 flex items-center justify-between text-[10px] font-bold text-neutral-400">
              <span className="tracking-wider uppercase">AXI4-LITE HARDWARE TUNING</span>
              {feedback && (
                <span className="text-[9px] text-emerald-400 bg-emerald-950/60 px-1.5 py-0.2 border border-emerald-800/60">
                  ✓ {feedback}
                </span>
              )}
            </div>

            <div className="p-3 space-y-3">
              {/* Strategy Mode Switcher */}
              <div className="space-y-1">
                <div className="text-[10px] text-neutral-500 uppercase">Strategy Mode Selection</div>
                <div className="grid grid-cols-2 gap-1">
                  <button
                    onClick={() => setStrategyMode('AVELLANEDA_STOIKOV')}
                    className={`py-1 text-[10px] font-bold border transition-colors ${
                      strategyMode === 'AVELLANEDA_STOIKOV'
                        ? 'bg-neutral-800 border-neutral-600 text-neutral-100'
                        : 'bg-neutral-900/60 border-neutral-800 text-neutral-500 hover:text-neutral-300'
                    }`}
                  >
                    Avellaneda-Stoikov
                  </button>
                  <button
                    onClick={() => setStrategyMode('OBI_MOMENTUM')}
                    className={`py-1 text-[10px] font-bold border transition-colors ${
                      strategyMode === 'OBI_MOMENTUM'
                        ? 'bg-neutral-800 border-neutral-600 text-neutral-100'
                        : 'bg-neutral-900/60 border-neutral-800 text-neutral-500 hover:text-neutral-300'
                    }`}
                  >
                    OBI Momentum
                  </button>
                </div>
              </div>

              {/* Sliders */}
              <div className="space-y-2">
                <div>
                  <div className="flex justify-between text-[10px] text-neutral-400">
                    <span>Risk Aversion (γ)</span>
                    <span className="font-bold text-neutral-100">{skewFactor}x</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="10"
                    step="1"
                    value={skewFactor}
                    onChange={(e) => setSkewFactor(Number(e.target.value))}
                    className="w-full h-1 bg-neutral-800 appearance-none accent-neutral-300 cursor-pointer"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[10px] text-neutral-400">
                    <span>Half-Spread (δ)</span>
                    <span className="font-bold text-neutral-100">${(halfSpread / 10000).toFixed(4)}</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="500"
                    step="10"
                    value={halfSpread}
                    onChange={(e) => setHalfSpread(Number(e.target.value))}
                    className="w-full h-1 bg-neutral-800 appearance-none accent-neutral-300 cursor-pointer"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[10px] text-neutral-400">
                    <span>Max Inventory (Q_max)</span>
                    <span className="font-bold text-neutral-100">±{maxInventory} shares</span>
                  </div>
                  <input
                    type="range"
                    min="500"
                    max="5000"
                    step="500"
                    value={maxInventory}
                    onChange={(e) => setMaxInventory(Number(e.target.value))}
                    className="w-full h-1 bg-neutral-800 appearance-none accent-neutral-300 cursor-pointer"
                  />
                </div>
              </div>

              {/* Apply Button */}
              <button
                onClick={() => handleApplyAxi()}
                disabled={isApplying}
                className="w-full py-1.5 bg-neutral-100 hover:bg-white text-neutral-950 font-bold text-xs uppercase tracking-wider transition-colors"
              >
                {isApplying ? 'WRITING REGISTERS...' : 'APPLY PARAMETERS (1-CYCLE)'}
              </button>
            </div>
          </div>
        </div>

        {/* ================================================================= */}
        {/* PANE 3 (RIGHT, 4 COLS): OUCH 5.0 TRADE BLOTTER                    */}
        {/* ================================================================= */}
        <div className="lg:col-span-4 flex flex-col h-full bg-[#06080d] divide-y divide-neutral-800/80 overflow-hidden">
          
          <div className="h-7 px-3 bg-[#0c0f17] border-b border-neutral-800/80 flex items-center justify-between text-[10px] font-bold text-neutral-400 shrink-0">
            <div className="flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-neutral-400" />
              <span className="tracking-wider uppercase">OUCH 5.0 TRADE BLOTTER</span>
              <span className="text-neutral-500">({orders.length})</span>
            </div>
            {lastOrder && (
              <span className="text-neutral-300 tabular-nums">
                {lastOrder.latency_cycles} cyc ({lastOrder.latency_ns.toFixed(0)}ns)
              </span>
            )}
          </div>

          {/* Continuous Orders Table */}
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-[#090b12] sticky top-0 border-b border-neutral-800 text-neutral-500 text-[9px] uppercase tracking-wider">
                <tr>
                  <th className="py-1 px-2">Ref</th>
                  <th className="py-1 px-2">Side</th>
                  <th className="py-1 px-2">Shares</th>
                  <th className="py-1 px-2">Price</th>
                  <th className="py-1 px-2">Latency</th>
                  <th className="py-1 px-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800/40 text-[10px]">
                {orders.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-12 text-neutral-600">
                      NO HARDWARE ORDERS GENERATED
                    </td>
                  </tr>
                ) : (
                  orders.map((ord) => {
                    const isExecuted = ord.status === 'EXECUTED';
                    const isBuy = ord.side === 'B';

                    return (
                      <tr key={ord.id} className="hover:bg-neutral-800/30 transition-colors">
                        <td className="py-1 px-2 text-neutral-400 tabular-nums">
                          #{ord.user_ref_num.toString().slice(-5)}
                        </td>
                        <td className="py-1 px-2">
                          <span
                            className={`px-1 py-0.2 text-[9px] font-bold ${
                              isBuy ? 'text-emerald-400 bg-emerald-950/40' : 'text-rose-400 bg-rose-950/40'
                            }`}
                          >
                            {isBuy ? 'BUY' : 'SELL'}
                          </span>
                        </td>
                        <td className="py-1 px-2 text-neutral-300 tabular-nums">{ord.shares.toLocaleString()}</td>
                        <td className="py-1 px-2 font-bold text-white tabular-nums">${ord.price.toFixed(2)}</td>
                        <td className="py-1 px-2 text-neutral-300 tabular-nums font-mono">
                          {ord.latency_cycles}c ({ord.latency_ns.toFixed(0)}ns)
                        </td>
                        <td className="py-1 px-2">
                          <span
                            className={`text-[9px] px-1 py-0.2 ${
                              isExecuted ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {ord.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
