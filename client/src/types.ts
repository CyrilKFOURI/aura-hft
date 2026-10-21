export interface RunLaunchRequest {
  dataset_name: string;
  symbol: string;
  obi_threshold: number;
  max_shares: number;
  price_collar: number;
  max_notional: number;
  kill_switch: boolean;
  scenario: string;
  tick_limit: number;
}

export interface RunResponse {
  id: string;
  created_at: string;
  dataset_name: string;
  symbol: string;
  obi_threshold: number;
  max_shares: number;
  price_collar: number;
  max_notional: number;
  kill_switch: boolean;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED';
  total_ticks: number;
  total_orders: number;
  p50_latency: number | null;
  p99_latency: number | null;
}

export interface DatasetInfo {
  name: string;
  symbol: string;
  description: string;
  tick_count: number;
  scenario_type: string;
}

export interface Top5Depth {
  bids: [number, number][]; // [price, shares]
  asks: [number, number][]; // [price, shares]
}

export interface TickData {
  id: number;
  run_id: string;
  timestamp_ns: number;
  cycle_count: number;
  msg_type: string;
  best_bid: number;
  best_ask: number;
  bid_qty_l1: number;
  ask_qty_l1: number;
  obi_value: number;
  micro_price: number;
  queue_pos: number | null;
  top_5?: Top5Depth;
}

export interface OrderData {
  id: number;
  run_id: string;
  user_ref_num: number;
  timestamp_ns: number;
  side: 'B' | 'S';
  shares: number;
  price: number;
  latency_cycles: number;
  latency_ns: number;
  status: 'EXECUTED' | 'REJECTED';
  risk_reason: string | null;
}

export interface ReplayStatus {
  run_id: string;
  state: 'PLAYING' | 'PAUSED' | 'COMPLETED';
  current_index: number;
  total_ticks: number;
  speed: number;
  progress_pct: number;
}

export interface AxiLiteStatus {
  kill_switch: boolean;
  skew_factor: number;
  half_spread: number;
  max_inventory: number;
  max_order_shares: number;
  strategy_mode: string;
  active_inventory: number;
  reservation_price: number;
  best_bid: number;
  best_ask: number;
  total_orders_approved: number;
  total_orders_rejected: number;
  arbitrated_orders: number;
  collision_count: number;
  telemetry_source: string;
}

export interface AxiLiteTuneRequest {
  kill_switch?: boolean;
  skew_factor?: number;
  half_spread?: number;
  max_inventory?: number;
  max_order_shares?: number;
  strategy_mode?: string;
}

// ---- Step P6: latency provenance and live feed
export interface FpgaLatency {
  kind: 'simulated';
  cycles: number;
  clock_mhz: number;
  ns: number;
  scope: string;
  source: string;
}

export interface DataSource {
  kind: string;
  name: string;
  date: string;
  file: string;
}

export interface SoftwareLatency {
  kind: 'measured';
  symbol: string;
  events: number;
  messages: number;
  p50_ns: number | null;
  p99_ns: number | null;
  p999_ns: number | null;
  mean_ns: number | null;
  max_ns: number | null;
  throughput_msgs_per_s: number | null;
  timer_overhead_ns: number | null;
  cpu: string;
  histogram: [number, number, number][]; // [lower_ns, upper_ns, count]
  data_source: DataSource;
  source: string;
}

export interface LatencySummary {
  fpga: FpgaLatency;
  software: SoftwareLatency[];
}

export interface LiveStatus {
  state: 'idle' | 'connecting' | 'live' | 'offline' | 'disabled';
  feed: string | null;
  url: string | null;
  instrument: string | null;
  mode: string;
  updates: number;
  reconnects: number;
  last_update: string | null;
  last_error: string | null;
  signals: { buy: number; sell: number };
  software_latency_ns: { kind: string; samples: number; p50: number | null; p99: number | null; p999: number | null };
}

export interface LiveTick {
  source: string;
  instrument: string;
  ts: string;
  bids: [number, number][];
  asks: [number, number][];
  obi: number | null;
  signal: { valid: boolean; buy: boolean; sell: boolean };
  sw_latency_ns: number;
  updates: number;
}

