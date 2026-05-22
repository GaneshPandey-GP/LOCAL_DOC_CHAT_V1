import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import MarkdownMessage from "@/components/MarkdownMessage";
import {
    CaretDown,
    CaretRight,
    Globe,
    DeviceMobile,
    DeviceTablet,
    Desktop,
    Fingerprint,
    Eye,
    LinkSimple,
    Clock,
    ChatCircleDots,
    Users,
    UserCircle,
    FileText,
    MagnifyingGlass,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const DEVICE_ICON = {
    mobile: DeviceMobile,
    tablet: DeviceTablet,
    desktop: Desktop,
};

function StatusBadge({ session }) {
    if (session.link_revoked) return <Badge variant="destructive" className="text-[10px] font-mono">REVOKED</Badge>;
    if (session.link_expires_at && new Date(session.link_expires_at) < new Date())
        return <Badge variant="secondary" className="text-[10px] font-mono">EXPIRED</Badge>;
    return <Badge className="text-[10px] font-mono bg-confidence-high">ACTIVE</Badge>;
}

function LinkStatus({ link }) {
    if (link.revoked) return <Badge variant="destructive" className="text-[10px] font-mono">REVOKED</Badge>;
    if (link.expires_at && new Date(link.expires_at) < new Date())
        return <Badge variant="secondary" className="text-[10px] font-mono">EXPIRED</Badge>;
    return <Badge className="text-[10px] font-mono bg-confidence-high">ACTIVE</Badge>;
}

function SessionDetail({ sessionId, open, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!open || !sessionId) return;
        setLoading(true);
        api.get(`/v2/share-links/history/sessions/${sessionId}`)
            .then((r) => setData(r.data))
            .catch(() => toast.error("Could not load session"))
            .finally(() => setLoading(false));
    }, [open, sessionId]);

    const s = data?.session || {};
    const link = data?.link || {};
    const msgs = data?.messages || [];
    const Icon = DEVICE_ICON[s.device_type] || Desktop;

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-hidden flex flex-col" data-testid="share-history-detail">
                <DialogHeader>
                    <DialogTitle className="font-heading">Guest session · {s.title || "Untitled"}</DialogTitle>
                    <DialogDescription className="font-mono text-[11px] truncate">{sessionId}</DialogDescription>
                </DialogHeader>

                {loading && <div className="text-sm text-muted-foreground">Loading…</div>}

                {!loading && data && (
                    <div className="overflow-auto space-y-5 pr-1">
                        {/* Visitor metadata */}
                        <section className="grid grid-cols-2 md:grid-cols-4 gap-3 border border-border p-4 bg-secondary/30">
                            <div>
                                <div className="dc-overline">IP</div>
                                <div className="font-mono text-sm" data-testid="detail-ip">{s.ip_masked || "—"}</div>
                            </div>
                            <div>
                                <div className="dc-overline">Location</div>
                                <div className="text-sm">{[s.geo_city, s.geo_country].filter(Boolean).join(", ") || "—"}</div>
                            </div>
                            <div>
                                <div className="dc-overline">Device</div>
                                <div className="flex items-center gap-1.5 text-sm capitalize">
                                    <Icon size={14} weight="duotone" />
                                    {s.device_type || "desktop"}
                                </div>
                            </div>
                            <div>
                                <div className="dc-overline">Fingerprint</div>
                                <div className="flex items-center gap-1.5 font-mono text-[11px]">
                                    <Fingerprint size={12} />
                                    {s.fingerprint ? s.fingerprint.slice(-6) : "—"}
                                </div>
                            </div>
                            <div className="col-span-2">
                                <div className="dc-overline">Browser / OS</div>
                                <div className="text-sm">
                                    {s.browser || "?"} {s.browser_version ? `v${s.browser_version}` : ""} ·{" "}
                                    {s.os || "?"} {s.os_version || ""}
                                </div>
                            </div>
                            <div className="col-span-2">
                                <div className="dc-overline">Started</div>
                                <div className="text-sm">{s.created_at ? new Date(s.created_at).toLocaleString() : "—"}</div>
                            </div>
                        </section>

                        {/* Documents in scope */}
                        <section>
                            <div className="dc-overline mb-2">Documents available to this session</div>
                            <div className="flex flex-wrap gap-2">
                                {(link.document_filenames || []).map((f, i) => (
                                    <span key={i} className="inline-flex items-center gap-1.5 border border-border bg-card px-2 py-1 text-xs">
                                        <FileText size={12} /> {f}
                                    </span>
                                ))}
                                {(link.document_filenames || []).length === 0 && (
                                    <span className="text-xs text-muted-foreground">No documents found</span>
                                )}
                            </div>
                        </section>

                        {/* Conversation */}
                        <section>
                            <div className="dc-overline mb-2">Conversation</div>
                            <div className="space-y-4">
                                {msgs.map((m) => (
                                    <div key={m.id} data-testid={`detail-msg-${m.role}`}>
                                        {m.role === "user" ? (
                                            <div className="flex justify-end">
                                                <div className="bg-secondary border border-border px-3 py-2 rounded-sm max-w-[85%] text-sm">{m.content}</div>
                                            </div>
                                        ) : (
                                            <div className="border-l-2 border-brand-primary pl-4">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <div className="dc-overline">DocChat</div>
                                                    {m.confidence && <ConfidenceBadge level={m.confidence} />}
                                                </div>
                                                <MarkdownMessage content={m.content} citations={m.citations || []} />
                                                {m.citations?.length > 0 && (
                                                    <div className="mt-3 space-y-1 text-xs">
                                                        <div className="dc-overline mb-1">Sources</div>
                                                        {m.citations.map((c) => (
                                                            <div key={c.chunk_id} className="flex items-center gap-2 py-1 px-2 border border-border rounded-sm">
                                                                <span className="font-mono text-[11px] bg-secondary border border-border px-1.5 py-0.5">[{c.index}]</span>
                                                                <FileText size={12} />
                                                                <span className="truncate flex-1">{c.filename}</span>
                                                                <span className="text-muted-foreground font-mono">p.{c.page}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                ))}
                                {msgs.length === 0 && (
                                    <div className="text-sm text-muted-foreground italic">No messages yet.</div>
                                )}
                            </div>
                        </section>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

export default function ShareHistory() {
    const [sessions, setSessions] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);

    const [search, setSearch] = useState("");
    const [linkFilter, setLinkFilter] = useState("all");
    const [statusFilter, setStatusFilter] = useState("all");
    const [creatorFilter, setCreatorFilter] = useState("all");
    const [deviceFilter, setDeviceFilter] = useState("all");
    const [dateFilter, setDateFilter] = useState("all"); // all | today | 7d | 30d
    const [sortBy, setSortBy] = useState("recent"); // recent | most_messages | oldest
    const [expanded, setExpanded] = useState({}); // { share_token: bool }
    const [activeSession, setActiveSession] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const [s, sum] = await Promise.all([
                api.get("/v2/share-links/history/sessions"),
                api.get("/v2/share-links/history/summary"),
            ]);
            setSessions(s.data || []);
            setSummary(sum.data || null);
        } catch (e) {
            if (e?.response?.status !== 403) toast.error("Could not load history");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    // Distinct dropdown options
    const linkOptions = useMemo(() => {
        const m = new Map();
        for (const s of sessions) {
            if (!m.has(s.share_token)) m.set(s.share_token, s.link_title || "(untitled)");
        }
        return Array.from(m.entries()).map(([id, title]) => ({ id, title }));
    }, [sessions]);

    const creatorOptions = useMemo(() => {
        const m = new Map();
        for (const s of sessions) {
            if (!s.creator_id) continue;
            if (!m.has(s.creator_id)) m.set(s.creator_id, s.creator_name || s.creator_email || s.creator_id);
        }
        return Array.from(m.entries()).map(([id, name]) => ({ id, name }));
    }, [sessions]);

    const sessionStatus = (s) => {
        if (s.link_revoked) return "revoked";
        if (s.link_expires_at && new Date(s.link_expires_at) < new Date()) return "expired";
        return "active";
    };

    const dateAfter = useMemo(() => {
        const now = new Date();
        if (dateFilter === "today") {
            const d = new Date(now); d.setHours(0, 0, 0, 0); return d;
        }
        if (dateFilter === "7d") return new Date(now.getTime() - 7 * 24 * 3600 * 1000);
        if (dateFilter === "30d") return new Date(now.getTime() - 30 * 24 * 3600 * 1000);
        return null;
    }, [dateFilter]);

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        let list = sessions.filter((s) => {
            if (linkFilter !== "all" && s.share_token !== linkFilter) return false;
            if (statusFilter !== "all" && sessionStatus(s) !== statusFilter) return false;
            if (creatorFilter !== "all" && s.creator_id !== creatorFilter) return false;
            if (deviceFilter !== "all" && (s.device_type || "desktop") !== deviceFilter) return false;
            if (dateAfter && s.last_activity && new Date(s.last_activity) < dateAfter) return false;
            if (q) {
                const hay = [
                    s.link_title, s.creator_name, s.creator_email,
                    s.ip_masked, s.geo_city, s.geo_country,
                    s.fingerprint, s.title,
                    ...(s.document_filenames || []),
                ].filter(Boolean).join(" ").toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });
        if (sortBy === "most_messages") {
            list = [...list].sort((a, b) => (b.message_count || 0) - (a.message_count || 0));
        } else if (sortBy === "oldest") {
            list = [...list].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
        } else {
            list = [...list].sort((a, b) => new Date(b.last_activity || 0) - new Date(a.last_activity || 0));
        }
        return list;
    }, [sessions, search, linkFilter, statusFilter, creatorFilter, deviceFilter, dateAfter, sortBy]);

    // Group filtered sessions by share-link token
    const groupedByLink = useMemo(() => {
        const groups = new Map();
        for (const s of filtered) {
            if (!groups.has(s.share_token)) {
                groups.set(s.share_token, {
                    share_token: s.share_token,
                    title: s.link_title || "(untitled)",
                    mode: s.link_mode,
                    revoked: s.link_revoked,
                    expires_at: s.link_expires_at,
                    creator_name: s.creator_name,
                    creator_role: s.creator_role,
                    document_filenames: s.document_filenames,
                    sessions: [],
                    total_messages: 0,
                    first_activity: null,
                    last_activity: null,
                });
            }
            const g = groups.get(s.share_token);
            g.sessions.push(s);
            g.total_messages += s.message_count || 0;
            const start = s.created_at ? new Date(s.created_at) : null;
            const last = s.last_activity ? new Date(s.last_activity) : null;
            if (start && (!g.first_activity || start < g.first_activity)) g.first_activity = start;
            if (last && (!g.last_activity || last > g.last_activity)) g.last_activity = last;
        }
        return Array.from(groups.values());
    }, [filtered]);

    const toggle = (token) => setExpanded((s) => ({ ...s, [token]: !s[token] }));

    return (
        <div>
            <header className="h-16 border-b border-border px-8 flex items-center justify-between sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Audit</div>
                    <h1 className="font-heading font-bold text-lg">Share Link History</h1>
                </div>
            </header>

            <div className="p-8 max-w-7xl">
                {/* Stats bar */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-0 border-l border-t border-border mb-6" data-testid="share-history-stats">
                    <Stat label="Total share links" value={summary?.total_links ?? "—"} icon={LinkSimple} />
                    <Stat label="Unique guest sessions" value={summary?.total_sessions ?? "—"} icon={Users} />
                    <Stat label="Total messages" value={summary?.total_messages ?? "—"} icon={ChatCircleDots} />
                    <Stat
                        label="Most active link"
                        value={summary?.most_active_link?.title || "—"}
                        sub={summary?.most_active_link ? `${summary.most_active_link.messages} msgs` : null}
                        icon={UserCircle}
                    />
                </div>

                {/* Filter row */}
                <div className="flex flex-wrap items-end gap-3 mb-5" data-testid="share-history-filters">
                    <div className="flex-1 min-w-[220px]">
                        <Label className="dc-overline">Search</Label>
                        <div className="relative mt-1">
                            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                placeholder="Link, IP, city, fingerprint, document…"
                                className="h-9 pl-8"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                data-testid="share-history-search"
                            />
                        </div>
                    </div>
                    <FilterSelect label="Link" value={linkFilter} onChange={setLinkFilter} testId="filter-link"
                        options={[{ value: "all", label: "All" }, ...linkOptions.map((l) => ({ value: l.id, label: l.title }))]} />
                    <FilterSelect label="Status" value={statusFilter} onChange={setStatusFilter} testId="filter-status"
                        options={[{ value: "all", label: "All" }, { value: "active", label: "Active" }, { value: "revoked", label: "Revoked" }, { value: "expired", label: "Expired" }]} />
                    <FilterSelect label="Creator" value={creatorFilter} onChange={setCreatorFilter} testId="filter-creator"
                        options={[{ value: "all", label: "All" }, ...creatorOptions.map((c) => ({ value: c.id, label: c.name }))]} />
                    <FilterSelect label="Device" value={deviceFilter} onChange={setDeviceFilter} testId="filter-device"
                        options={[{ value: "all", label: "All" }, { value: "desktop", label: "Desktop" }, { value: "tablet", label: "Tablet" }, { value: "mobile", label: "Mobile" }]} />
                    <FilterSelect label="Date" value={dateFilter} onChange={setDateFilter} testId="filter-date"
                        options={[{ value: "all", label: "All time" }, { value: "today", label: "Today" }, { value: "7d", label: "Last 7 days" }, { value: "30d", label: "Last 30 days" }]} />
                    <FilterSelect label="Sort" value={sortBy} onChange={setSortBy} testId="filter-sort"
                        options={[{ value: "recent", label: "Most recent" }, { value: "most_messages", label: "Most messages" }, { value: "oldest", label: "Oldest first" }]} />
                </div>

                {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
                {!loading && groupedByLink.length === 0 && (
                    <div className="border border-dashed border-border p-12 text-center text-sm text-muted-foreground" data-testid="share-history-empty">
                        No guest sessions match the current filters.
                    </div>
                )}

                <div className="space-y-3">
                    {groupedByLink.map((g) => {
                        const isOpen = !!expanded[g.share_token];
                        return (
                            <div key={g.share_token} className="border border-border" data-testid={`history-link-${g.share_token}`}>
                                <button
                                    type="button"
                                    onClick={() => toggle(g.share_token)}
                                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-secondary/30 transition-colors text-left"
                                    data-testid={`history-link-toggle-${g.share_token}`}
                                >
                                    {isOpen ? <CaretDown size={14} /> : <CaretRight size={14} />}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-medium truncate">{g.title}</span>
                                            <LinkStatus link={{ revoked: g.revoked, expires_at: g.expires_at }} />
                                            {g.mode && <Badge variant="outline" className="text-[10px] font-mono uppercase">{g.mode}</Badge>}
                                        </div>
                                        <div className="text-xs text-muted-foreground mt-0.5">
                                            By {g.creator_name || "—"} · {g.sessions.length} session{g.sessions.length === 1 ? "" : "s"} · {g.total_messages} msgs
                                            {g.last_activity && ` · last ${g.last_activity.toLocaleDateString()}`}
                                        </div>
                                        {g.document_filenames?.length > 0 && (
                                            <div className="text-[11px] text-muted-foreground mt-0.5 truncate" title={g.document_filenames.join(", ")}>
                                                Docs: {g.document_filenames.slice(0, 3).join(", ")}{g.document_filenames.length > 3 && ` +${g.document_filenames.length - 3}`}
                                            </div>
                                        )}
                                    </div>
                                </button>

                                {isOpen && (
                                    <div className="border-t border-border bg-secondary/10">
                                        <div className="hidden md:grid grid-cols-[40px_140px_180px_140px_70px_180px_90px] gap-3 px-4 py-2 text-xs font-mono uppercase tracking-wider text-muted-foreground border-b border-border">
                                            <div>#</div>
                                            <div>IP</div>
                                            <div>Location</div>
                                            <div>Device</div>
                                            <div>Msgs</div>
                                            <div>Last activity</div>
                                            <div></div>
                                        </div>
                                        {g.sessions.map((s, i) => {
                                            const Icon = DEVICE_ICON[s.device_type || "desktop"] || Desktop;
                                            return (
                                                <div
                                                    key={s.session_id}
                                                    className="md:grid md:grid-cols-[40px_140px_180px_140px_70px_180px_90px] gap-3 px-4 py-2.5 border-b border-border last:border-b-0 items-center text-sm"
                                                    data-testid={`history-session-${s.session_id}`}
                                                >
                                                    <div className="font-mono text-xs text-muted-foreground">#{i + 1}</div>
                                                    <div className="font-mono text-xs">{s.ip_masked || "—"}</div>
                                                    <div className="flex items-center gap-1.5">
                                                        <Globe size={12} className="text-muted-foreground" />
                                                        <span className="text-xs truncate">{[s.geo_city, s.geo_country].filter(Boolean).join(", ") || "—"}</span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5 min-w-0">
                                                        <Icon size={14} weight="duotone" />
                                                        <span className="text-xs capitalize">{s.device_type || "desktop"}</span>
                                                        <span className="text-[10px] font-mono text-muted-foreground truncate">{s.browser || "?"}</span>
                                                    </div>
                                                    <div className="font-mono text-xs">{s.message_count}</div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {s.last_activity ? new Date(s.last_activity).toLocaleString() : "—"}
                                                    </div>
                                                    <div className="flex items-center gap-1.5 justify-end">
                                                        {s.fingerprint && (
                                                            <span className="font-mono text-[10px] text-muted-foreground" title={s.fingerprint}>
                                                                {s.fingerprint.slice(-6)}
                                                            </span>
                                                        )}
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="h-7 px-2 gap-1"
                                                            onClick={() => setActiveSession(s.session_id)}
                                                            data-testid={`view-session-${s.session_id}`}
                                                        >
                                                            <Eye size={12} /> View
                                                        </Button>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>

            <SessionDetail
                sessionId={activeSession}
                open={!!activeSession}
                onClose={() => setActiveSession(null)}
            />
        </div>
    );
}

function Stat({ label, value, sub, icon: Icon }) {
    return (
        <div className="border-r border-b border-border p-5 bg-card flex items-start gap-3">
            {Icon && <Icon size={22} weight="duotone" className="text-muted-foreground shrink-0 mt-0.5" />}
            <div className="min-w-0">
                <div className="dc-overline">{label}</div>
                <div className="font-heading font-bold text-2xl truncate" title={typeof value === "string" ? value : undefined}>{value}</div>
                {sub && <div className="text-[11px] font-mono text-muted-foreground">{sub}</div>}
            </div>
        </div>
    );
}

function FilterSelect({ label, value, onChange, options, testId }) {
    return (
        <div className="w-[150px]">
            <Label className="dc-overline">{label}</Label>
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger className="mt-1 h-9" data-testid={testId}>
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    {options.map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </div>
    );
}
