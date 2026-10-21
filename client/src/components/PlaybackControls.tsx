import React from 'react';
import { Play, Pause, SkipBack, SkipForward, RotateCcw, FastForward, Activity } from 'lucide-react';
import type { ReplayStatus } from '../types';
import { TickerDropdown } from './TickerDropdown';

interface PlaybackControlsProps {
  status: ReplayStatus;
  play: (speed?: number) => void;
  pause: () => void;
  step: (dir: number) => void;
  seek: (index: number) => void;
  setSpeed: (speed: number) => void;
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
}

export const PlaybackControls: React.FC<PlaybackControlsProps> = ({
  status,
  play,
  pause,
  step,
  seek,
  setSpeed,
  selectedTicker,
  onSelectTicker,
}) => {
  const isPlaying = status.state === 'PLAYING';
  const speeds = [0.5, 1.0, 2.0, 5.0, 10.0];

  return (
    <div className="bg-[#0b0f19] border border-slate-800/80 rounded-lg p-2.5 font-mono shadow-sm flex flex-col gap-2 select-none">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Ticker Dropdown & Transport controls */}
        <div className="flex items-center gap-2">
          {/* Integrated Ticker Dropdown */}
          <TickerDropdown
            selectedTicker={selectedTicker}
            onSelectTicker={onSelectTicker}
          />

          <div className="h-5 w-[1px] bg-slate-800 mx-1 hidden sm:block"></div>

          {/* Transport buttons */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => (isPlaying ? pause() : play(status.speed))}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-bold text-xs transition-all shadow-sm ${
                isPlaying
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30'
                  : 'bg-cyan-500 text-slate-950 hover:bg-cyan-400'
              }`}
              title={isPlaying ? 'Pause replay' : 'Play feed'}
            >
              {isPlaying ? (
                <>
                  <Pause className="w-3.5 h-3.5 fill-current" />
                  <span>PAUSE</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>PLAY</span>
                </>
              )}
            </button>

            <button
              onClick={() => step(-1)}
              disabled={status.current_index <= 0}
              className="p-1.5 rounded-md bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-30 transition-colors"
              title="Step -1 tick"
            >
              <SkipBack className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => step(1)}
              disabled={status.current_index >= status.total_ticks - 1}
              className="p-1.5 rounded-md bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-30 transition-colors"
              title="Step +1 tick"
            >
              <SkipForward className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => seek(0)}
              className="p-1.5 rounded-md bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              title="Rewind to start"
            >
              <RotateCcw className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Right: Speed pills & Tick counter */}
        <div className="flex items-center gap-3">
          {/* Speed selector */}
          <div className="flex items-center gap-0.5 bg-slate-900/90 border border-slate-800/80 p-0.5 rounded-md">
            <FastForward className="w-3 h-3 text-slate-500 ml-1 mr-0.5" />
            {speeds.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setSpeed(s);
                  if (isPlaying) play(s);
                }}
                className={`px-1.5 py-0.5 rounded text-[10px] font-bold transition-all ${
                  status.speed === s
                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Tick progress badge */}
          <div className="flex items-center gap-2 text-xs bg-slate-900/90 border border-slate-800/80 px-2.5 py-1 rounded-md text-slate-300">
            <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
            <span className="text-slate-400 text-[11px]">TICK</span>
            <span className="font-bold text-white text-[11px]">
              {status.current_index + 1}
              <span className="text-slate-500 font-normal">/{status.total_ticks}</span>
            </span>
            <span className="text-cyan-400 font-bold text-[11px]">
              {status.progress_pct.toFixed(0)}%
            </span>
          </div>
        </div>
      </div>

      {/* Sleek inline scrubber slider */}
      <div className="w-full flex items-center pt-0.5">
        <input
          type="range"
          min={0}
          max={Math.max(0, status.total_ticks - 1)}
          value={status.current_index}
          onChange={(e) => seek(Number(e.target.value))}
          className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 focus:outline-none hover:bg-slate-700 transition-colors"
        />
      </div>
    </div>
  );
};
