import { useState, useEffect, useRef, useCallback } from 'react';
import type { TickData, OrderData, ReplayStatus } from '../types';

export function useReplayWebSocket(runId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [currentTick, setCurrentTick] = useState<TickData | null>(null);
  const [lastOrder, setLastOrder] = useState<OrderData | null>(null);
  const [status, setStatus] = useState<ReplayStatus>({
    run_id: runId || '',
    state: 'PAUSED',
    current_index: 0,
    total_ticks: 0,
    speed: 1.0,
    progress_pct: 0,
  });

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // Handle both dev server with proxy and direct port 8000
    const wsUrl = `${protocol}//${host}/ws/replay/${runId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'tick') {
          setCurrentTick(msg.data.tick);
          if (msg.data.order) {
            setLastOrder(msg.data.order);
          }
          setStatus((prev) => ({
            ...prev,
            current_index: msg.data.index,
            progress_pct: prev.total_ticks > 0 ? (msg.data.index / prev.total_ticks) * 100 : 0,
          }));
        } else if (msg.type === 'status') {
          setStatus(msg.data);
        } else if (msg.type === 'completed') {
          setStatus((prev) => ({ ...prev, state: 'COMPLETED' }));
        }
      } catch (e) {
        console.error('Error parsing WS message', e);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  const sendCommand = useCallback((cmd: Record<string, unknown>) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  const play = useCallback((speed?: number) => {
    sendCommand({ action: 'play', speed });
  }, [sendCommand]);

  const pause = useCallback(() => {
    sendCommand({ action: 'pause' });
  }, [sendCommand]);

  const step = useCallback((direction: number = 1) => {
    sendCommand({ action: 'step', direction });
  }, [sendCommand]);

  const seek = useCallback((tickIndex: number) => {
    sendCommand({ action: 'seek', tick_index: tickIndex });
  }, [sendCommand]);

  const setSpeed = useCallback((speed: number) => {
    sendCommand({ action: 'set_speed', speed });
  }, [sendCommand]);

  return {
    isConnected,
    currentTick,
    lastOrder,
    status,
    play,
    pause,
    step,
    seek,
    setSpeed,
  };
}
