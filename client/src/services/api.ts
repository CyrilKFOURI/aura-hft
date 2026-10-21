import type { DatasetInfo, LatencySummary, RunLaunchRequest, RunResponse, TickData, OrderData } from '../types';

const API_BASE = '/api';

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Failed to reach backend');
  return res.json();
}

export async function fetchDatasets(): Promise<DatasetInfo[]> {
  const res = await fetch(`${API_BASE}/datasets`);
  if (!res.ok) throw new Error('Failed to fetch datasets');
  return res.json();
}

export async function fetchRuns(): Promise<RunResponse[]> {
  const res = await fetch(`${API_BASE}/runs`);
  if (!res.ok) throw new Error('Failed to fetch runs');
  return res.json();
}

export async function fetchRun(runId: string): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/runs/${runId}`);
  if (!res.ok) throw new Error(`Run ${runId} not found`);
  return res.json();
}

export async function fetchRunTicks(runId: string, offset = 0, limit = 500): Promise<TickData[]> {
  const res = await fetch(`${API_BASE}/runs/${runId}/ticks?offset=${offset}&limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch ticks');
  return res.json();
}

export async function fetchRunOrders(runId: string): Promise<OrderData[]> {
  const res = await fetch(`${API_BASE}/runs/${runId}/orders`);
  if (!res.ok) throw new Error('Failed to fetch orders');
  return res.json();
}

export async function launchRun(request: RunLaunchRequest): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/runs/launch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to launch run: ${errorText}`);
  }
  return res.json();
}

export async function fetchLatency(): Promise<LatencySummary> {
  const res = await fetch(`${API_BASE}/latency`);
  if (!res.ok) throw new Error('Failed to fetch latency summary');
  return res.json();
}

export async function fetchAxiLiteStatus(): Promise<any> {
  const res = await fetch(`${API_BASE}/axi-lite/status`);
  if (!res.ok) throw new Error('Failed to fetch AXI-Lite status');
  return res.json();
}

export async function tuneAxiLite(params: any): Promise<any> {
  const res = await fetch(`${API_BASE}/axi-lite/tune`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to tune AXI-Lite registers');
  return res.json();
}

