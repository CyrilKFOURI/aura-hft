import React from 'react';

interface MultiTickerSelectorProps {
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
}

const TICKERS = [
  { symbol: 'AAPL', locate: 1, name: 'Apple Inc.', color: 'border-blue-500 text-blue-400' },
  { symbol: 'MSFT', locate: 2, name: 'Microsoft Corp.', color: 'border-emerald-500 text-emerald-400' },
  { symbol: 'NVDA', locate: 3, name: 'NVIDIA Corp.', color: 'border-purple-500 text-purple-400' },
  { symbol: 'TSLA', locate: 4, name: 'Tesla Inc.', color: 'border-amber-500 text-amber-400' },
];

export const MultiTickerSelector: React.FC<MultiTickerSelectorProps> = ({
  selectedTicker,
  onSelectTicker,
}) => {
  return (
    <div className="bg-[#121622] border border-slate-800 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 shadow-lg">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
          Concurrent 4-Symbol FPGA Feed:
        </span>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {TICKERS.map((t) => {
          const isActive = selectedTicker === t.symbol;
          return (
            <button
              key={t.symbol}
              onClick={() => onSelectTicker(t.symbol)}
              className={`px-4 py-2 rounded-lg font-mono text-xs font-semibold transition-all flex items-center gap-2 border ${
                isActive
                  ? `bg-slate-800/90 text-white shadow-md ${t.color}`
                  : 'bg-slate-900/40 border-slate-800/80 text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <span className="font-bold text-sm">{t.symbol}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                LOC #{t.locate}
              </span>
              {isActive && (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
