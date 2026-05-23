import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChartBar, Robot, Coin, Clock, Warning } from "@phosphor-icons/react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";

const RANGES = [
    { label: "Last 7d", value: 7 },
    { label: "Last 30d", value: 30 },
    { label: "Last 90d", value: 90 },
];

export default function ModelAnalytics() {
    const [days, setDays] = useState(7);
    const [summary, setSummary] = useState(null);
    const [byModel, setByModel] = useState([]);
    const [latency, setLatency] = useState([]);
    const [cost, setCost] = useState([]);

    const load = async () => {
        const [s, b, l, c] = await Promise.all([
            api.get(`/v2/model-analytics/summary?days=${days}`),
            api.get(`/v2/model-analytics/by-model?days=${days}`),
            api.get(`/v2/model-analytics/latency?days=${days}`),
            api.get(`/v2/model-analytics/cost?days=${days}`),
        ]);
        setSummary(s.data); setByModel(b.data); setLatency(l.data); setCost(c.data);
    };
    useEffect(() => { load(); }, [days]);

    // Build daily-by-day line chart data: { day, [model_id]: calls }
    const daily = useMemo(() => {
        const days_map = {};
        const models = new Set();
        for (const r of cost) {
            models.add(r.model_id);
            if (!days_map[r.day]) days_map[r.day] = { day: r.day };
            days_map[r.day][r.model_id] = (days_map[r.day][r.model_id] || 0) + r.calls;
        }
        return { rows: Object.values(days_map).sort((a, b) => a.day.localeCompare(b.day)), models: [...models] };
    }, [cost]);

    const COLORS = ["#0033A0", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6"];

    return (
        <div>
            <header className="h-auto md:h-16 border-b border-border px-4 md:px-8 py-3 md:py-0 flex flex-col md:flex-row md:items-center justify-between gap-3 sticky top-0 bg-background z-10">
                <div className="flex items-center gap-3">
                    <ChartBar size={22} weight="duotone" className="text-brand-primary" />
                    <div><div className="dc-overline">Admin</div><h1 className="font-heading font-bold text-lg">Model Analytics</h1></div>
                </div>
                <Select value={String(days)} onValueChange={v => setDays(+v)}>
                    <SelectTrigger className="w-[160px]"><SelectValue /></SelectTrigger>
                    <SelectContent>{RANGES.map(r => <SelectItem key={r.value} value={String(r.value)}>{r.label}</SelectItem>)}</SelectContent>
                </Select>
            </header>

            <div className="p-4 md:p-8 max-w-6xl space-y-6">
                <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                    {[
                        { label: "Calls", val: summary?.calls ?? 0, icon: Robot },
                        { label: "Tokens", val: (summary?.tokens || 0).toLocaleString(), icon: ChartBar },
                        { label: "Cost (USD)", val: "$" + ((summary?.cost ?? 0).toFixed(4)), icon: Coin },
                        { label: "Avg latency (ms)", val: summary?.avg_latency ?? 0, icon: Clock },
                        { label: "Error rate", val: (summary?.error_rate ?? 0) + "%", icon: Warning },
                    ].map(s => (
                        <div key={s.label} className="border border-border p-3" data-testid={`stat-${s.label.toLowerCase().replace(/\s+/g, '-')}`}>
                            <div className="flex items-center justify-between"><div className="dc-overline">{s.label}</div><s.icon size={14} className="text-brand-primary" /></div>
                            <div className="font-heading font-bold text-xl mt-1 truncate">{s.val}</div>
                        </div>
                    ))}
                </div>

                <div className="border border-border p-4">
                    <div className="dc-overline mb-3">Daily Call Volume by Model</div>
                    {daily.rows.length === 0 ? <div className="text-sm text-muted-foreground">No calls recorded yet.</div> : (
                        <ResponsiveContainer width="100%" height={260}>
                            <LineChart data={daily.rows}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="day" fontSize={10} />
                                <YAxis fontSize={10} />
                                <Tooltip />
                                <Legend />
                                {daily.models.map((m, i) => <Line key={m} type="monotone" dataKey={m} stroke={COLORS[i % COLORS.length]} dot={false} />)}
                            </LineChart>
                        </ResponsiveContainer>
                    )}
                </div>

                <div className="border border-border p-4">
                    <div className="dc-overline mb-3">Cost per Model</div>
                    {byModel.length === 0 ? <div className="text-sm text-muted-foreground">No data.</div> : (
                        <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={byModel}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="model_id" fontSize={10} />
                                <YAxis fontSize={10} />
                                <Tooltip />
                                <Bar dataKey="cost" fill="#0033A0" />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </div>

                <div className="border border-border">
                    <div className="px-4 py-3 dc-overline border-b border-border">Per-model Breakdown</div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-secondary/50 text-xs font-mono uppercase text-muted-foreground">
                                <tr><th className="text-left px-3 py-2">Model</th><th className="text-left px-3 py-2">Provider</th><th className="text-right px-3 py-2">Calls</th><th className="text-right px-3 py-2">Tokens</th><th className="text-right px-3 py-2">Cost</th><th className="text-right px-3 py-2">Avg Latency</th><th className="text-right px-3 py-2">Success %</th></tr>
                            </thead>
                            <tbody>
                                {byModel.length === 0 ? <tr><td colSpan={7} className="p-4 text-center text-muted-foreground">No metrics yet.</td></tr> :
                                    byModel.map(r => (
                                        <tr key={r.model_id} className="border-t border-border">
                                            <td className="px-3 py-2 font-mono text-xs">{r.model_id}</td>
                                            <td className="px-3 py-2 text-xs">{r.provider}</td>
                                            <td className="px-3 py-2 text-right font-mono">{r.calls}</td>
                                            <td className="px-3 py-2 text-right font-mono">{r.tokens.toLocaleString()}</td>
                                            <td className="px-3 py-2 text-right font-mono">${r.cost.toFixed(4)}</td>
                                            <td className="px-3 py-2 text-right font-mono">{r.avg_latency} ms</td>
                                            <td className="px-3 py-2 text-right"><Badge variant="outline">{r.success_rate}%</Badge></td>
                                        </tr>
                                    ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="border border-border p-4">
                    <div className="dc-overline mb-3">Latency Distribution (p50 / p90 / p99)</div>
                    {latency.length === 0 ? <div className="text-sm text-muted-foreground">No latency data.</div> : (
                        <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={latency}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="model_id" fontSize={10} />
                                <YAxis fontSize={10} />
                                <Tooltip />
                                <Legend />
                                <Bar dataKey="p50" fill="#10b981" />
                                <Bar dataKey="p90" fill="#f59e0b" />
                                <Bar dataKey="p99" fill="#ef4444" />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </div>
            </div>
        </div>
    );
}
