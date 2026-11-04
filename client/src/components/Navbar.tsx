import React from 'react';
import { Cpu, Terminal, Sliders, BarChart2 } from 'lucide-react';

interface NavbarProps {
  currentTab: 'launcher' | 'replay' | 'analytics';
  setCurrentTab: (tab: 'launcher' | 'replay' | 'analytics') => void;
  isConnected: boolean;
  activeRunId: string | null;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  setCurrentTab,
  isConnected,
  activeRunId,
}) => {
  return (
    <header className="h-9 min-h-[36px] bg-[#08090d] border-b border-neutral-800/80 px-3 flex items-center justify-between text-xs font-mono select-none z-30">
      {/* Brand & Platform Spec */}
      <div className="flex items-center space-x-3 text-neutral-300">
        <div className="flex items-center space-x-2">
          <Cpu className="w-3.5 h-3.5 text-neutral-400" />
          <span className="font-semibold tracking-wider text-neutral-100 text-[11px]">
            AURA<span className="text-neutral-400">::HFT</span>
          </span>
        </div>
        <span className="text-neutral-700">/</span>
        <div className="flex items-center space-x-1.5 text-[10px] text-neutral-400">
          <span className="text-neutral-300 font-medium">KRIA KR260</span>
          <span className="text-neutral-600">·</span>
          <span>156.25 MHz</span>
          <span className="text-neutral-600">·</span>
          <span>6.4ns/cyc</span>
        </div>
      </div>

      {/* Navigation tabs - Clean flat hairline tabs */}
      <nav className="flex items-center h-full">
        <button
          onClick={() => setCurrentTab('launcher')}
          className={`h-full px-3.5 flex items-center space-x-1.5 text-[11px] font-medium transition-colors border-b-2 ${
            currentTab === 'launcher'
              ? 'border-neutral-200 text-neutral-100 bg-neutral-900/40'
              : 'border-transparent text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/20'
          }`}
        >
          <Sliders className="w-3 h-3" />
          <span>CONFIG</span>
        </button>

        <button
          onClick={() => setCurrentTab('replay')}
          disabled={!activeRunId}
          className={`h-full px-3.5 flex items-center space-x-1.5 text-[11px] font-medium transition-colors border-b-2 ${
            currentTab === 'replay'
              ? 'border-neutral-200 text-neutral-100 bg-neutral-900/40'
              : !activeRunId
              ? 'border-transparent text-neutral-600 cursor-not-allowed'
              : 'border-transparent text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/20'
          }`}
        >
          <Terminal className="w-3 h-3" />
          <span>TERMINAL</span>
          {activeRunId && (
            <span className="text-[9px] text-neutral-400 bg-neutral-800/80 px-1 py-0.2 rounded-sm ml-0.5">
              #{activeRunId.slice(0, 4)}
            </span>
          )}
        </button>

        <button
          onClick={() => setCurrentTab('analytics')}
          disabled={!activeRunId}
          className={`h-full px-3.5 flex items-center space-x-1.5 text-[11px] font-medium transition-colors border-b-2 ${
            currentTab === 'analytics'
              ? 'border-neutral-200 text-neutral-100 bg-neutral-900/40'
              : !activeRunId
              ? 'border-transparent text-neutral-600 cursor-not-allowed'
              : 'border-transparent text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900/20'
          }`}
        >
          <BarChart2 className="w-3 h-3" />
          <span>BENCHMARKS</span>
        </button>
      </nav>

      {/* Hardware Status Strip */}
      <div className="flex items-center space-x-3 text-[10px]">
        <div className="flex items-center space-x-1.5 text-neutral-400">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isConnected ? 'bg-emerald-400' : 'bg-amber-400'
            }`}
          />
          <span className="text-neutral-500">FEED</span>
          <span className={isConnected ? 'text-neutral-200 font-medium' : 'text-amber-400'}>
            {isConnected ? 'ONLINE' : 'STANDBY'}
          </span>
        </div>

        <span className="text-neutral-800">|</span>

        <div className="flex items-center space-x-1.5 text-neutral-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          <span className="text-neutral-500">FPGA</span>
          <span className="text-neutral-200 font-medium">ARMED</span>
        </div>
      </div>
    </header>
  );
};
