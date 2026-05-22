import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, CartesianGrid } from "recharts";
import { ChartLine, FileText, UsersThree, LinkSimple, ChatCircle } from "@phosphor-icons/react";

function StatCard({ label, value, icon: Icon, testId }) {
    return (
        <div className="border border-border p-6" data-testid={testId}>
            <div className="flex items-center justify-between">
                <div className="dc-overline">{label}</div>
                <Icon size={18} weight="duotone" className="text-muted-foreground" />
            </div>
            <div className="font-heading font-black text-4xl tracking-tighter mt-2">{value}</div>
        </div>
    );
}

export default function AdminAnalytics() {
    const [data, setData] = useState(null);

    useEffect(() => {
        api.get("/admin/analytics", { params: { days: 14 } }).then((r) => setData(r.data)).catch(() => {});
    }, []);

    if (!data) {
        return (
            <div>
                <header className="h-16 border-b border-border px-8 flex items-center">
                    <div>
                        <div className="dc-overline">Admin</div>
                        <h1 className="font-heading font-bold text-lg">Analytics</h1>
                    </div>
                </header>
                <div className="p-8 text-sm text-muted-foreground">Loading metrics…</div>
            </div>
        );
    }

    const { totals, latency_ms, feedback, queries_daily, confidence_distribution } = data;
    const confSeries = Object.entries(confidence_distribution || {}).map(([k, v]) => ({ level: k, count: v }));

    return (
        <div>
            <header className="h-16 border-b border-border px-8 flex items-center sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Admin</div>
                    <h1 className="font-heading font-bold text-lg">Analytics</h1>
                </div>
            </header>

            <div className="p-8 max-w-7xl space-y-8">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-0 border-l border-t border-border">
                    {[
                        { label: "Documents", value: totals.documents, icon: FileText, testId: "stat-documents" },
                        { label: "Users", value: totals.users, icon: UsersThree, testId: "stat-users" },
                        { label: "Sessions", value: totals.sessions, icon: ChatCircle, testId: "stat-sessions" },
                        { label: "Share links", value: totals.share_links, icon: LinkSimple, testId: "stat-shares" },
                        { label: "Messages (14d)", value: totals.messages, icon: ChartLine, testId: "stat-messages" },
                    ].map((s, i) => (
                        <div key={i} className="border-r border-b border-border p-6" data-testid={s.testId}>
                            <div className="flex items-center justify-between">
                                <div className="dc-overline">{s.label}</div>
                                <s.icon size={18} weight="duotone" className="text-muted-foreground" />
                            </div>
                            <div className="font-heading font-black text-4xl tracking-tighter mt-2">{s.value}</div>
                        </div>
                    ))}
                </div>

                <div className="grid md:grid-cols-2 gap-0 border-l border-t border-border">
                    <div className="border-r border-b border-border p-6" data-testid="chart-queries-daily">
                        <div className="dc-overline mb-1">Queries per day</div>
                        <div className="font-heading font-bold text-2xl mb-4">Last 14 days</div>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={queries_daily}>
                                    <CartesianGrid stroke="#E5E7EB" strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="day" tickFormatter={(d) => d.slice(5)} style={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#9CA3AF" />
                                    <YAxis allowDecimals={false} style={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#9CA3AF" />
                                    <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                                    <Line type="monotone" dataKey="count" stroke="#0033A0" strokeWidth={2} dot={{ r: 3, fill: "#0033A0" }} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="border-r border-b border-border p-6" data-testid="chart-confidence-distribution">
                        <div className="dc-overline mb-1">Confidence distribution</div>
                        <div className="font-heading font-bold text-2xl mb-4">Answer grounding</div>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={confSeries}>
                                    <CartesianGrid stroke="#E5E7EB" strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="level" style={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#9CA3AF" />
                                    <YAxis allowDecimals={false} style={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="#9CA3AF" />
                                    <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                                    <Bar dataKey="count" fill="#0033A0" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="border-r border-b border-border p-6" data-testid="latency-stats">
                        <div className="dc-overline mb-1">Response latency</div>
                        <div className="font-heading font-bold text-2xl mb-4">End-to-end (ms)</div>
                        <div className="grid grid-cols-3 gap-4">
                            {["p50", "p90", "p99"].map((k) => (
                                <div key={k} className="border border-border p-4">
                                    <div className="dc-overline">{k}</div>
                                    <div className="font-heading font-black text-3xl mt-1">{latency_ms[k] || 0}</div>
                                </div>
                            ))}
                        </div>
                        <div className="text-xs text-muted-foreground mt-3 font-mono">{latency_ms.samples} samples</div>
                    </div>

                    <div className="border-r border-b border-border p-6" data-testid="feedback-stats">
                        <div className="dc-overline mb-1">User feedback</div>
                        <div className="font-heading font-bold text-2xl mb-4">Thumbs ratio</div>
                        <div className="flex items-end gap-4">
                            <div>
                                <div className="font-heading font-black text-6xl tracking-tighter text-brand-primary">
                                    {Math.round((feedback.ratio || 0) * 100)}%
                                </div>
                                <div className="text-xs font-mono text-muted-foreground mt-1">positive rate</div>
                            </div>
                            <div className="flex-1 space-y-2 pb-2">
                                <div className="flex items-center gap-2 text-sm">
                                    <span className="text-confidence-high font-mono">▲</span> {feedback.up} up
                                </div>
                                <div className="flex items-center gap-2 text-sm">
                                    <span className="text-confidence-low font-mono">▼</span> {feedback.down} down
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
