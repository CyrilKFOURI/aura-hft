import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

interface TickerDropdownProps {
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
}

export const TICKERS = [
  { symbol: 'AAPL', locate: 1, name: 'Apple Inc.', color: 'text-sky-400' },
  { symbol: 'MSFT', locate: 2, name: 'Microsoft Corp.', color: 'text-emerald-400' },
  { symbol: 'NVDA', locate: 3, name: 'NVIDIA Corp.', color: 'text-purple-400' },
  { symbol: 'TSLA', locate: 4, name: 'Tesla Inc.', color: 'text-amber-400' },
];

export const TickerDropdown: React.FC<TickerDropdownProps> = ({
  selectedTicker,
  onSelectTicker,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const active = TICKERS.find((t) => t.symbol === selectedTicker) || TICKERS[0];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative font-mono" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2.5 px-3 py-1.5 rounded-md bg-slate-900/90 border border-slate-700/80 hover:border-slate-500 text-xs transition-colors shadow-sm select-none"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
        <span className="font-bold text-sm tracking-wide text-white">{active.symbol}</span>
        <span className="text-[11px] text-slate-400 hidden sm:inline">{active.name}</span>
        <span className="text-[10px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/60">
          LOC #{active.locate}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-1.5 w-64 rounded-lg bg-[#0e131f] border border-slate-700/80 shadow-2xl z-50 overflow-hidden divide-y divide-slate-800/80 animate-in fade-in zoom-in-95 duration-100">
          <div className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-950/60">
            Select Active Feed Symbol
          </div>
          <div className="py-1">
            {TICKERS.map((t) => {
              const isSelected = t.symbol === selectedTicker;
              return (
                <button
                  key={t.symbol}
                  onClick={() => {
                    onSelectTicker(t.symbol);
                    setIsOpen(false);
                  }}
                  className={`w-full px-3 py-2 text-left flex items-center justify-between text-xs hover:bg-slate-800/70 transition-colors ${
                    isSelected ? 'bg-slate-800/50 text-white' : 'text-slate-300'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`font-bold ${t.color}`}>{t.symbol}</span>
                    <span className="text-[11px] text-slate-400">{t.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                      #{t.locate}
                    </span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-emerald-400" />}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
