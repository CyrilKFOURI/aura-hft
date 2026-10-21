import { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { Launcher } from './components/Launcher';
import { AnalyticsView } from './components/AnalyticsView';
import { TerminalWorkspace } from './components/TerminalWorkspace';
import { useReplayWebSocket } from './hooks/useReplayWebSocket';
import { fetchRuns, fetchRunOrders } from './services/api';
import type { RunResponse, OrderData } from './types';

export function App() {
  const [currentTab, setCurrentTab] = useState<'launcher' | 'replay' | 'analytics'>('replay');
  const [activeRun, setActiveRun] = useState<RunResponse | null>(null);
  const [orders, setOrders] = useState<OrderData[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string>('AAPL');

  // Hook for active run websocket streaming
  const {
    isConnected,
    currentTick,
    lastOrder,
    status,
    play,
    pause,
    step,
    seek,
    setSpeed,
  } = useReplayWebSocket(activeRun?.id ?? null);

  // Load existing runs on initial mount
  useEffect(() => {
    fetchRuns()
      .then((runs) => {
        if (runs.length > 0) {
          const latest = runs[0];
          setActiveRun(latest);
          fetchRunOrders(latest.id).then(setOrders).catch(console.error);
        }
      })
      .catch(console.error);
  }, []);

  const handleRunLaunched = (run: RunResponse) => {
    setActiveRun(run);
    fetchRunOrders(run.id).then(setOrders).catch(console.error);
    setCurrentTab('replay');
  };

  const handleSelectHistoricalRun = (run: RunResponse) => {
    setActiveRun(run);
    fetchRunOrders(run.id).then(setOrders).catch(console.error);
    setCurrentTab('replay');
  };

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#07080c] text-neutral-300 flex flex-col font-mono selection:bg-neutral-700/50">
      {/* Top Navbar */}
      <Navbar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        isConnected={isConnected}
        activeRunId={activeRun?.id ?? null}
      />

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden w-full">
        {currentTab === 'launcher' && (
          <Launcher onRunLaunched={handleRunLaunched} />
        )}

        {currentTab === 'replay' && (
          <TerminalWorkspace
            status={status}
            tick={currentTick}
            orders={orders}
            lastOrder={lastOrder}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
            play={play}
            pause={pause}
            step={step}
            seek={seek}
            setSpeed={setSpeed}
            obiThreshold={activeRun?.obi_threshold ?? 0.65}
          />
        )}

        {currentTab === 'analytics' && (
          <AnalyticsView
            currentRun={activeRun}
            onSelectRun={handleSelectHistoricalRun}
          />
        )}
      </main>
    </div>
  );
}

export default App;
