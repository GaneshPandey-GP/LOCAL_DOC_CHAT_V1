import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { MagnifyingGlass } from "@phosphor-icons/react";

export default function AdminAudit() {
    const [events, setEvents] = useState([]);
    const [q, setQ] = useState("");

    useEffect(() => {
        api.get("/admin/audit-log", { params: { limit: 200 } }).then((r) => setEvents(r.data)).catch(() => {});
    }, []);

    const filtered = events.filter((e) => {
        if (!q) return true;
        const blob = [e.action, e.actor_id, e.resource_type, e.resource_id].filter(Boolean).join(" ").toLowerCase();
        return blob.includes(q.toLowerCase());
    });

    return (
        <div>
            <header className="h-16 border-b border-border px-8 flex items-center justify-between sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Admin</div>
                    <h1 className="font-heading font-bold text-lg">Audit log</h1>
                </div>
                <div className="relative w-72">
                    <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <Input placeholder="Filter by action, actor, resource…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9 h-9" data-testid="audit-search-input" />
                </div>
            </header>

            <div className="p-8 max-w-7xl">
                <div className="border border-border">
                    <div className="hidden md:grid grid-cols-[160px_180px_100px_1fr_140px] gap-4 px-4 py-3 bg-secondary/50 border-b border-border text-xs font-mono uppercase tracking-wider text-muted-foreground">
                        <div>Timestamp</div>
                        <div>Action</div>
                        <div>Role</div>
                        <div>Resource</div>
                        <div>IP</div>
                    </div>
                    {filtered.length === 0 && (
                        <div className="p-6 text-sm text-muted-foreground" data-testid="audit-empty">No events.</div>
                    )}
                    {filtered.map((e) => (
                        <div
                            key={e.id}
                            className="md:grid md:grid-cols-[160px_180px_100px_1fr_140px] gap-4 px-4 py-3 border-b border-border last:border-b-0 hover:bg-secondary/30 text-[13px] font-mono"
                            data-testid={`audit-row-${e.id}`}
                        >
                            <div className="text-muted-foreground">{new Date(e.created_at).toLocaleString()}</div>
                            <div className="font-medium">{e.action}</div>
                            <div className="uppercase text-muted-foreground">{e.actor_role || "—"}</div>
                            <div className="truncate">
                                <span className="text-muted-foreground">{e.resource_type || "—"}</span>{" "}
                                <span>{e.resource_id || ""}</span>
                            </div>
                            <div className="text-muted-foreground">{e.ip || "—"}</div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
