import { useEffect, useState } from 'react';
import type { LiveStatus, LiveTick } from '../types';

// Subscribes to /ws/live (public crypto L2 book + software OBI, paper only).
// The backend opens the upstream connection only while a client is subscribed.
export function useLiveFeed(enabled: boolean) {
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [tick, setTick] = useState<LiveTick | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/live`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'live_status') setStatus(msg.data as LiveStatus);
        else if (msg.type === 'live_tick') setTick(msg.data as LiveTick);
      } catch (err) {
        console.error('live feed message', err);
      }
    };
    return () => ws.close();
  }, [enabled]);

  return { status, tick, connected };
}
