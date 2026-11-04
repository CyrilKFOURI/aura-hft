import React, { useState } from 'react';
import { Radio } from 'lucide-react';
import { useLiveFeed } from '../hooks/useLiveFeed';

const fmtNs = (v: number | null | undefined) => (v == null ? '—' : `${(v / 1000).toFixed(1)} µs`);

const STATE_COLOR: Record<string, string> = {
  live: 'text-emerald-400',
  connecting: 'text-amber-400',
  offline: 'text-rose-400',
  idle: 'text-neutral-500',
  disabled: 'text-neutral-500',
};

// Live public crypto L2 book with the software OBI rule (same Q1.31 rule as the RTL).
// Paper only: the backend reads market data and never sends an order.
export const LiveFeedPanel: React.FC = () => {
  const [enabled, setEnabled] = useState(false);
  const { status, tick, connected } = useLiveFeed(enabled);
  const state = enabled ? status?.state ?? (connected ? 'connecting' : 'offline') : 'idle';
  const sig = tick?.signal;

  return (
    <div className="border-b border-neutral-800/80 bg-[#08090d]">
      <div className="px-3.5 py-2 bg-[#090b10] border-b border-neutral-800/80 flex items-center justify-between">
        <span className="text-[10px] uppercase font-bold tracking-wider text-neutral-400 flex items-center space-x-1.5">
          <Radio className="w-3 h-3" />
          <span>LIVE CRYPTO FEED · SOFTWARE OBI (PAPER ONLY)</span>
        </span>
        <button
          type="button"
          onClick={() => setEnabled((v) => !v)}
          className="px-2 py-0.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-[10px]"
        >
          {enabled ? 'DISCONNECT' : 'CONNECT'}
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 divide-x divide-neutral-800/80 text-[11px]">
        <div className="px-3.5 py-2">
          <div className="text-[9px] uppercase text-neutral-500">SOURCE</div>
          <div className="text-neutral-200 truncate">{status?.feed ?? tick?.source ?? '—'}</div>
          <div className={`text-[9px] uppercase ${STATE_COLOR[state] ?? 'text-neutral-500'}`}>
            {state}{status?.last_error && state !== 'live' ? ` · ${status.last_error}` : ''}
          </div>
        </div>
        <div className="px-3.5 py-2">
          <div className="text-[9px] uppercase text-neutral-500">BEST BID / ASK</div>
          <div className="text-neutral-100 font-bold">
            {tick?.bids[0] ? tick.bids[0][0].toFixed(2) : '—'} / {tick?.asks[0] ? tick.asks[0][0].toFixed(2) : '—'}
          </div>
          <div className="text-[9px] text-neutral-500">
            {tick?.bids[0] ? tick.bids[0][1] : '—'} × {tick?.asks[0] ? tick.asks[0][1] : '—'}
          </div>
        </div>
        <div className="px-3.5 py-2">
          <div className="text-[9px] uppercase text-neutral-500">OBI (L1)</div>
          <div className="text-neutral-100 font-bold">{tick?.obi != null ? tick.obi.toFixed(3) : '—'}</div>
          <div className="text-[9px] text-neutral-500">
            {sig ? (sig.buy ? 'BUY signal' : sig.sell ? 'SELL signal' : 'no signal') : '—'} · thresholds ±0.40
          </div>
        </div>
        <div className="px-3.5 py-2">
          <div className="text-[9px] uppercase text-neutral-500">SIGNALS (SESSION)</div>
          <div className="text-neutral-100 font-bold">
            {status ? `${status.signals.buy} / ${status.signals.sell}` : '—'}
          </div>
          <div className="text-[9px] text-neutral-500">buy / sell · {status?.updates ?? 0} book updates</div>
        </div>
        <div className="px-3.5 py-2">
          <div className="text-[9px] uppercase text-neutral-500">PYTHON PATH P50 / P99 / P99.9</div>
          <div className="text-neutral-100 font-bold">
            {fmtNs(status?.software_latency_ns.p50)} / {fmtNs(status?.software_latency_ns.p99)} /{' '}
            {fmtNs(status?.software_latency_ns.p999)}
          </div>
          <div className="text-[9px] text-neutral-500">measured, normalize + book + OBI</div>
        </div>
      </div>
    </div>
  );
};
