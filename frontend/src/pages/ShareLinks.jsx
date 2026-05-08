import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
    Plus,
    Copy,
    Trash,
    LinkSimple,
    Lock,
    Clock,
    Globe,
    WarningCircle,
    Check,
} from "@phosphor-icons/react";

function CreateDialog({ open, onOpenChange, onCreated }) {
    const [docs, setDocs] = useState([]);
    const [selected, setSelected] = useState([]);
    const [mode, setMode] = useState("public");
    const [title, setTitle] = useState("");
    const [password, setPassword] = useState("");
    const [expiresIn, setExpiresIn] = useState("24");
    const [singleUse, setSingleUse] = useState(false);
    const [domain, setDomain] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!open) return;
        api.get("/v2/documents").then((r) => setDocs(r.data.filter((d) => d.status === "ready")));
        setSelected([]); setMode("public"); setTitle(""); setPassword(""); setExpiresIn("24"); setSingleUse(false); setDomain("");
    }, [open]);

    const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

    const submit = async () => {
        if (!selected.length) { toast.error("Select at least one document"); return; }
        if (mode === "password" && !password) { toast.error("Password required"); return; }
        setBusy(true);
        try {
            await api.post("/v2/share-links", {
                document_ids: selected,
                mode,
                password: mode === "password" ? password : undefined,
                expires_in_hours: mode === "expiring" ? parseInt(expiresIn, 10) : undefined,
                single_use: singleUse,
                domain_restriction: domain || undefined,
                title: title || undefined,
            });
            toast.success("Share link created");
            onOpenChange(false);
            onCreated?.();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Create failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg" data-testid="create-share-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">Create share link</DialogTitle>
                    <DialogDescription>Tokenized access to an exact subset of documents. Revocable anytime.</DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    <div>
                        <Label className="dc-overline">Link title (optional)</Label>
                        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Q4 investor review" className="mt-1" data-testid="share-title-input" />
                    </div>

                    <div>
                        <Label className="dc-overline">Documents</Label>
                        <div className="mt-1 border border-border max-h-48 overflow-auto">
                            {docs.length === 0 && <div className="p-3 text-xs text-muted-foreground">No ready documents available.</div>}
                            {docs.map((d) => (
                                <label
                                    key={d.id}
                                    className="flex items-center gap-3 px-3 py-2 border-b border-border last:border-b-0 hover:bg-secondary/50 cursor-pointer"
                                    data-testid={`share-doc-${d.id}`}
                                >
                                    <input
                                        type="checkbox"
                                        checked={selected.includes(d.id)}
                                        onChange={() => toggle(d.id)}
                                        className="w-4 h-4 accent-brand-primary"
                                    />
                                    <span className="text-sm truncate">{d.filename}</span>
                                </label>
                            ))}
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-1 font-mono">
                            {selected.length} selected
                        </div>
                    </div>

                    <div>
                        <Label className="dc-overline">Access mode</Label>
                        <Select value={mode} onValueChange={setMode}>
                            <SelectTrigger className="mt-1" data-testid="share-mode-select">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="public">Public · anyone with link</SelectItem>
                                <SelectItem value="password">Password · requires passphrase</SelectItem>
                                <SelectItem value="expiring">Expiring · valid for N hours</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {mode === "password" && (
                        <div>
                            <Label className="dc-overline">Passphrase</Label>
                            <Input type="text" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1" data-testid="share-password-input" />
                        </div>
                    )}

                    {mode === "expiring" && (
                        <div>
                            <Label className="dc-overline">Valid for (hours)</Label>
                            <Input type="number" min={1} max={720} value={expiresIn} onChange={(e) => setExpiresIn(e.target.value)} className="mt-1" data-testid="share-expiry-input" />
                        </div>
                    )}

                    <div>
                        <Label className="dc-overline">Domain restriction (optional)</Label>
                        <Input
                            value={domain}
                            onChange={(e) => setDomain(e.target.value)}
                            placeholder="@company.com"
                            className="mt-1 font-mono"
                            data-testid="share-domain-input"
                        />
                    </div>

                    <div className="flex items-center justify-between border border-border px-3 py-2.5 rounded-sm">
                        <div>
                            <div className="text-sm font-medium">Single-use link</div>
                            <div className="text-xs text-muted-foreground">Invalidates after first open</div>
                        </div>
                        <Switch checked={singleUse} onCheckedChange={setSingleUse} data-testid="share-single-use-switch" />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="share-cancel-button">Cancel</Button>
                    <Button onClick={submit} disabled={busy} data-testid="share-create-submit-button">
                        {busy ? "Creating…" : "Create link"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function ModeIcon({ mode }) {
    if (mode === "password") return <Lock size={14} weight="duotone" />;
    if (mode === "expiring") return <Clock size={14} weight="duotone" />;
    return <Globe size={14} weight="duotone" />;
}

export default function ShareLinks() {
    const [links, setLinks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [createOpen, setCreateOpen] = useState(false);
    const [copied, setCopied] = useState(null);

    // Filters
    const [statusFilter, setStatusFilter] = useState("all");
    const [modeFilter, setModeFilter] = useState("all");
    const [creatorFilter, setCreatorFilter] = useState("all"); // "all" | "owner" | <userId>
    const [searchQ, setSearchQ] = useState("");

    const load = async () => {
        setLoading(true);
        try {
            const r = await api.get("/v2/share-links");
            setLinks(r.data);
        } catch (e) {
            if (e?.response?.status !== 403) toast.error("Failed to load links");
        } finally { setLoading(false); }
    };

    useEffect(() => { load(); }, []);

    const copy = (t) => {
        const url = `${window.location.origin}/share/${t}`;
        navigator.clipboard.writeText(url);
        setCopied(t);
        toast.success("Copied share URL");
        setTimeout(() => setCopied(null), 2000);
    };

    const revoke = async (t) => {
        if (!window.confirm("Revoke this link? Active guests will lose access immediately.")) return;
        try {
            await api.delete(`/v2/share-links/${t}`);
            toast.success("Link revoked");
            setLinks((c) => c.map((l) => (l.token === t ? { ...l, revoked: true } : l)));
        } catch (e) {
            toast.error("Revoke failed");
        }
    };

    const linkStatus = (l) => {
        if (l.revoked) return "revoked";
        if (l.expires_at && new Date(l.expires_at) < new Date()) return "expired";
        if (l.single_use && (l.opens || 0) > 0) return "used";
        return "active";
    };

    // Distinct editor creators (excluding the "all/owner" buckets)
    const editorCreators = React.useMemo(() => {
        const map = new Map();
        for (const l of links) {
            if (l.creator_role !== "editor" || !l.creator_id) continue;
            if (!map.has(l.creator_id)) {
                map.set(l.creator_id, { id: l.creator_id, name: l.creator_name || l.creator_email || l.creator_id });
            }
        }
        return Array.from(map.values()).sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    }, [links]);

    const filtered = React.useMemo(() => {
        const q = searchQ.trim().toLowerCase();
        return links.filter((l) => {
            if (statusFilter !== "all" && linkStatus(l) !== statusFilter) return false;
            if (modeFilter !== "all" && l.mode !== modeFilter) return false;
            if (creatorFilter === "owner" && l.creator_role !== "owner") return false;
            if (creatorFilter !== "all" && creatorFilter !== "owner" && l.creator_id !== creatorFilter) return false;
            if (q) {
                const hay = [
                    l.title || "",
                    l.creator_name || "",
                    l.creator_email || "",
                    ...(l.document_filenames || []),
                ].join(" ").toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });
    }, [links, statusFilter, modeFilter, creatorFilter, searchQ]);

    return (
        <div>
            <header className="h-16 border-b border-border px-8 flex items-center justify-between sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Workspace</div>
                    <h1 className="font-heading font-bold text-lg">Share links</h1>
                </div>
                <Button onClick={() => setCreateOpen(true)} data-testid="create-share-button">
                    <Plus size={16} /> New link
                </Button>
            </header>

            <div className="p-8 max-w-7xl">
                <div className="border border-border bg-secondary/30 p-4 mb-6 flex items-start gap-3 text-sm" data-testid="share-security-notice">
                    <WarningCircle size={20} weight="duotone" className="text-confidence-medium shrink-0 mt-0.5" />
                    <div>
                        <div className="font-medium">Strict document scoping</div>
                        <div className="text-xs text-muted-foreground mt-1">
                            Every guest retrieval is enforced server-side against the token's document_ids. Guests cannot see or query anything else in your workspace.
                        </div>
                    </div>
                </div>

                {/* Filters */}
                <div className="flex flex-wrap items-end gap-3 mb-4" data-testid="share-filters">
                    <div className="flex-1 min-w-[200px]">
                        <Label className="dc-overline">Search</Label>
                        <Input
                            placeholder="Title, creator, or document name…"
                            value={searchQ}
                            onChange={(e) => setSearchQ(e.target.value)}
                            className="mt-1 h-9"
                            data-testid="share-filter-search"
                        />
                    </div>
                    <div className="w-[140px]">
                        <Label className="dc-overline">Status</Label>
                        <Select value={statusFilter} onValueChange={setStatusFilter}>
                            <SelectTrigger className="mt-1 h-9" data-testid="share-filter-status">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="active">Active</SelectItem>
                                <SelectItem value="revoked">Revoked</SelectItem>
                                <SelectItem value="used">Used</SelectItem>
                                <SelectItem value="expired">Expired</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="w-[140px]">
                        <Label className="dc-overline">Mode</Label>
                        <Select value={modeFilter} onValueChange={setModeFilter}>
                            <SelectTrigger className="mt-1 h-9" data-testid="share-filter-mode">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="public">Public</SelectItem>
                                <SelectItem value="password">Password</SelectItem>
                                <SelectItem value="expiring">Expiring</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="w-[180px]">
                        <Label className="dc-overline">Creator</Label>
                        <Select value={creatorFilter} onValueChange={setCreatorFilter}>
                            <SelectTrigger className="mt-1 h-9" data-testid="share-filter-creator">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="owner">Owner</SelectItem>
                                {editorCreators.map((e) => (
                                    <SelectItem key={e.id} value={e.id}>{e.name}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                </div>

                {loading && <div className="text-sm text-muted-foreground">Loading…</div>}

                {!loading && links.length === 0 && (
                    <div className="border border-dashed border-border p-16 text-center" data-testid="empty-shares">
                        <LinkSimple size={36} weight="duotone" className="mx-auto text-muted-foreground" />
                        <h2 className="font-heading font-bold text-xl mt-4">No share links yet</h2>
                        <p className="text-sm text-muted-foreground mt-2">Create a tokenized link scoped to specific documents.</p>
                        <Button className="mt-6" onClick={() => setCreateOpen(true)} data-testid="empty-create-share-button">
                            <Plus size={16} /> Create first link
                        </Button>
                    </div>
                )}

                {!loading && links.length > 0 && filtered.length === 0 && (
                    <div className="border border-dashed border-border p-12 text-center text-sm text-muted-foreground" data-testid="share-no-match">
                        No links match the current filters.
                    </div>
                )}

                {!loading && filtered.length > 0 && (
                    <div className="border border-border">
                        <div className="hidden md:grid grid-cols-[1fr_140px_110px_70px_80px_90px_140px] gap-4 px-4 py-3 bg-secondary/50 border-b border-border text-xs font-mono uppercase tracking-wider text-muted-foreground">
                            <div>Link</div>
                            <div>Creator</div>
                            <div>Mode</div>
                            <div>Docs</div>
                            <div>Opens</div>
                            <div>Status</div>
                            <div>Actions</div>
                        </div>
                        {filtered.map((l) => {
                            const url = `${window.location.origin}/share/${l.token}`;
                            const expired = l.expires_at && new Date(l.expires_at) < new Date();
                            const dead = l.revoked || expired || (l.single_use && l.opens > 0);
                            return (
                                <div
                                    key={l.token}
                                    className="md:grid md:grid-cols-[1fr_140px_110px_70px_80px_90px_140px] gap-4 px-4 py-3 border-b border-border last:border-b-0 items-center"
                                    data-testid={`share-link-row-${l.token}`}
                                >
                                    <div className="min-w-0">
                                        <div className="font-medium truncate">{l.title || "Untitled link"}</div>
                                        <div className="text-[11px] font-mono text-muted-foreground truncate">{url}</div>
                                        {l.document_filenames?.length > 0 && (
                                            <div className="text-[11px] text-muted-foreground truncate mt-0.5" title={l.document_filenames.join(", ")}>
                                                {l.document_filenames.slice(0, 2).join(", ")}
                                                {l.document_filenames.length > 2 && ` +${l.document_filenames.length - 2}`}
                                            </div>
                                        )}
                                    </div>
                                    <div className="min-w-0">
                                        <div className="text-sm truncate" data-testid={`share-link-creator-${l.token}`}>
                                            {l.creator_name || l.creator_email || "—"}
                                        </div>
                                        {l.creator_role && (
                                            <div className="text-[10px] font-mono uppercase text-muted-foreground">{l.creator_role}</div>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-1.5 text-xs font-mono uppercase">
                                        <ModeIcon mode={l.mode} /> {l.mode}
                                    </div>
                                    <div className="text-sm font-mono">{l.document_ids?.length || 0}</div>
                                    <div className="text-sm font-mono">{l.opens || 0}</div>
                                    <div>
                                        {l.revoked && <Badge variant="destructive" className="text-[10px] font-mono">REVOKED</Badge>}
                                        {!l.revoked && expired && <Badge variant="secondary" className="text-[10px] font-mono">EXPIRED</Badge>}
                                        {!l.revoked && !expired && l.single_use && l.opens > 0 && <Badge variant="secondary" className="text-[10px] font-mono">USED</Badge>}
                                        {!dead && <Badge className="text-[10px] font-mono bg-confidence-high">ACTIVE</Badge>}
                                    </div>
                                    <div className="flex gap-1">
                                        <Button size="sm" variant="outline" onClick={() => copy(l.token)} data-testid={`copy-share-${l.token}`} disabled={dead}>
                                            {copied === l.token ? <Check size={14} /> : <Copy size={14} />}
                                            <span className="ml-1">Copy</span>
                                        </Button>
                                        {!l.revoked && (
                                            <Button size="icon" variant="ghost" onClick={() => revoke(l.token)} data-testid={`revoke-share-${l.token}`}>
                                                <Trash size={14} />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <CreateDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={load} />
        </div>
    );
}
