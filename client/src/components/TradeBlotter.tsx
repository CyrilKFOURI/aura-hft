import React from 'react';
import type { OrderData } from '../types';
import { Zap, Clock, ShieldCheck, ShieldAlert } from 'lucide-react';

interface TradeBlotterProps {
  orders: OrderData[];
  lastOrder: OrderData | null;
}

export const TradeBlotter: React.FC<TradeBlotterProps> = ({ orders, lastOrder }) => {
  return (
    <div className="font-mono text-xs flex flex-col">
      {/* Header */}
      <div className="bg-slate-900/60 border-b border-slate-800/80 px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-slate-200 tracking-wide text-[11px]">
            OUCH 5.0 TRADE BLOTTER
          </span>
          <span className="text-[10px] bg-slate-800/80 text-slate-400 px-1.5 py-0.2 rounded border border-slate-700/50">
            {orders.length}
          </span>
        </div>

        {lastOrder && (
          <div className="flex items-center gap-1.5 text-[11px]">
            <Clock className="w-3 h-3 text-cyan-400" />
            <span className="text-slate-400">LAST:</span>
            <span className="text-cyan-300 font-bold">
              {lastOrder.latency_cycles} cyc ({lastOrder.latency_ns.toFixed(1)} ns)
            </span>
          </div>
        )}
      </div>

      {/* Orders Table */}
      <div className="overflow-x-auto max-h-[220px] overflow-y-auto">
        <table className="w-full text-left border-collapse">
          <thead className="bg-slate-950/80 sticky top-0 border-b border-slate-800 text-slate-400 text-[10px]">
            <tr>
              <th className="py-1.5 px-2.5">REF</th>
              <th className="py-1.5 px-2.5">TIME</th>
              <th className="py-1.5 px-2.5">SIDE</th>
              <th className="py-1.5 px-2.5">SHARES</th>
              <th className="py-1.5 px-2.5">PRICE</th>
              <th className="py-1.5 px-2.5">HW LATENCY</th>
              <th className="py-1.5 px-2.5">STATUS</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50 text-[11px]">
            {orders.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-6 text-slate-500">
                  NO HARDWARE ORDERS GENERATED YET
                </td>
              </tr>
            ) : (
              orders.map((ord) => {
                const isExecuted = ord.status === 'EXECUTED';
                const isBuy = ord.side === 'B';

                return (
                  <tr key={ord.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-1.5 px-2.5 text-slate-400 font-medium">
                      #{ord.user_ref_num.toString().slice(-6)}
                    </td>
                    <td className="py-1.5 px-2.5 text-slate-400">
                      {new Date(Math.floor(ord.timestamp_ns / 1_000_000)).toLocaleTimeString([], {
                        hour12: false,
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </td>
                    <td className="py-1.5 px-2.5">
                      <span
                        className={`px-1.5 py-0.2 rounded font-bold text-[10px] ${
                          isBuy ? 'text-emerald-400 bg-emerald-950/60' : 'text-rose-400 bg-rose-950/60'
                        }`}
                      >
                        {isBuy ? 'BUY' : 'SELL'}
                      </span>
                    </td>
                    <td className="py-1.5 px-2.5 text-slate-200">
                      {ord.shares.toLocaleString()}
                    </td>
                    <td className="py-1.5 px-2.5 font-bold text-white">
                      ${ord.price.toFixed(2)}
                    </td>
                    <td className="py-1.5 px-2.5 text-cyan-300 font-medium">
                      {ord.latency_cycles}c ({ord.latency_ns.toFixed(0)}ns)
                    </td>
                    <td className="py-1.5 px-2.5">
                      <span
                        className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.2 rounded ${
                          isExecuted
                            ? 'text-emerald-400 bg-emerald-950/40'
                            : 'text-rose-400 bg-rose-950/40'
                        }`}
                      >
                        {isExecuted ? <ShieldCheck className="w-3 h-3" /> : <ShieldAlert className="w-3 h-3" />}
                        {ord.status}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
