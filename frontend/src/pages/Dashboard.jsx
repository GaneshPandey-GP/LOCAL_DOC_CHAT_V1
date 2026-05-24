import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api, { API_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import UploadDialog, { DOCUMENT_CATEGORIES } from "@/components/UploadDialog";
import { toast } from "sonner";
import {
    Plus,
    MagnifyingGlass,
    FileText,
    FilePdf,
    FileDoc,
    FileXls,
    FilePpt,
    Image as ImageIcon,
    CheckCircle,
    Clock,
    XCircle,
    Trash,
    ChatCircle,
    ArrowClockwise,
    Eye,
    UserPlus,
    BookOpen,
} from "@phosphor-icons/react";

const IconForFile = ({ filename }) => {
    const ext = (filename || "").split(".").pop().toLowerCase();
    if (ext === "pdf") return <FilePdf size={22} weight="duotone" className="text-destructive" />;
    if (ext === "docx") return <FileDoc size={22} weight="duotone" className="text-brand-primary" />;
    if (ext === "pptx") return <FilePpt size={22} weight="duotone" className="text-confidence-medium" />;
    if (ext === "xlsx" || ext === "csv") return <FileXls size={22} weight="duotone" className="text-confidence-high" />;
    if (["png", "jpg", "jpeg"].includes(ext)) return <ImageIcon size={22} weight="duotone" className="text-brand-accent" />;
    return <FileText size={22} weight="duotone" className="text-muted-foreground" />;
};

const StatusBadge = ({ status }) => {
    if (status === "ready") return <span className="inline-flex items-center gap-1 text-xs font-mono text-confidence-high"><CheckCircle size={14} weight="fill" /> READY</span>;
    if (status === "failed") return <span className="inline-flex items-center gap-1 text-xs font-mono text-confidence-low"><XCircle size={14} weight="fill" /> FAILED</span>;
    return <span className="inline-flex items-center gap-1 text-xs font-mono text-confidence-medium"><Clock size={14} weight="fill" /> {String(status).toUpperCase()}</span>;
};

export default function Dashboard() {
    const { user: currentUser } = useAuth();
    const isOwner = currentUser?.role === "owner";

    const [docs, setDocs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [q, setQ] = useState("");
    const [uploadOpen, setUploadOpen] = useState(false);
    const [selected, setSelected] = useState([]);
    const [editors, setEditors] = useState([]);
    const [assignDoc, setAssignDoc] = useState(null);
    const [assignSelection, setAssignSelection] = useState([]);
    const [assignBusy, setAssignBusy] = useState(false);

    // Filters (Stream 4 — server-side AND composition)
    const [uploaderFilter, setUploaderFilter] = useState("all"); // all | self | <userId>
    const [accessFilter, setAccessFilter] = useState("all"); // all | self | assigned
    const [statusFilter, setStatusFilter] = useState("all"); // all | ready | processing | failed
    const [categoryFilter, setCategoryFilter] = useState("all"); // Stream 1
    const [kbFilter, setKbFilter] = useState("all");             // Mar 2026 — KB scope filter
    const [knowledgeBases, setKnowledgeBases] = useState([]);

    // Stream 2 — bulk assignment modal state
    const [bulkAssignOpen, setBulkAssignOpen] = useState(false);
    const [bulkSelection, setBulkSelection] = useState([]);
    const [bulkBusy, setBulkBusy] = useState(false);
    // Mar 2026 — bulk move-to-KB modal state
    const [bulkKbOpen, setBulkKbOpen] = useState(false);
    const [bulkKbTarget, setBulkKbTarget] = useState("__none__");
    const [bulkKbBusy, setBulkKbBusy] = useState(false);

    const load = async () => {
        try {
            // Stream 4 — push every active filter to the server in a single call
            const params = {};
            if (q) params.q = q;
            if (statusFilter !== "all") params.status = statusFilter;
            if (accessFilter !== "all") params.access = accessFilter;
            if (uploaderFilter !== "all") params.uploaded_by = uploaderFilter;
            if (categoryFilter !== "all") params.category = categoryFilter;
            if (kbFilter !== "all") params.kb_id = kbFilter;
            const r = await api.get("/v2/documents", { params });
            setDocs(r.data);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
        // Pull KBs once for the filter + bulk-move target picker.
        api.get("/v2/kb").then(r => setKnowledgeBases(r.data || [])).catch(() => {});
    }, []);
    useEffect(() => {
        // Debounce all filter+search changes into one server call (Stream 4).
        const id = setTimeout(load, 200);
        return () => clearTimeout(id);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [q, statusFilter, accessFilter, uploaderFilter, categoryFilter, kbFilter]);

    // Owners need the editor list to assign documents
    useEffect(() => {
        if (!isOwner) return;
        api.get("/admin/users").then((r) => {
            setEditors((r.data || []).filter((u) => u.role === "editor"));
        }).catch(() => {});
    }, [isOwner]);

    // Poll processing docs
    useEffect(() => {
        const processing = docs.filter((d) => d.status !== "ready" && d.status !== "failed");
        if (processing.length === 0) return;
        const id = setInterval(async () => {
            try {
                const updates = await Promise.all(
                    processing.map((d) => api.get(`/v2/documents/${d.id}/processing-status`).then((r) => ({ id: d.id, ...r.data })).catch(() => null))
                );
                setDocs((cur) =>
                    cur.map((d) => {
                        const u = updates.find((x) => x?.id === d.id);
                        return u ? { ...d, status: u.status, progress: u.progress, chunk_count: u.chunk_count, error: u.error } : d;
                    })
                );
            } catch {}
        }, 2500);
        return () => clearInterval(id);
    }, [docs]);

    const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

    const del = async (d) => {
        if (!window.confirm(`Delete "${d.filename}"? This removes the file and all embeddings.`)) return;
        try {
            await api.delete(`/v2/documents/${d.id}`);
            toast.success("Document deleted");
            setDocs((c) => c.filter((x) => x.id !== d.id));
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Delete failed");
        }
    };

    const retry = async (d) => {
        try {
            await api.post(`/v2/documents/${d.id}/reprocess`);
            toast.success(`Retrying "${d.filename}"…`);
            setDocs((c) => c.map((x) => x.id === d.id ? { ...x, status: "queued", progress: 5, error: null } : x));
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Retry failed");
        }
    };

    const chatSelected = () => {
        const ready = docs.filter((d) => selected.includes(d.id) && d.status === "ready");
        if (!ready.length) { toast.error("Select at least one ready document"); return; }
        const params = new URLSearchParams({ docs: ready.map((r) => r.id).join(",") });
        window.location.href = `/app/chat?${params}`;
    };

    const viewDocument = async (d) => {
        try {
            const token = localStorage.getItem("dc_access_token");
            const res = await fetch(`${API_BASE}/v2/documents/${d.id}/file`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const w = window.open(url, "_blank");
            if (!w) {
                // popup blocked — fall back to triggering download
                const a = document.createElement("a");
                a.href = url;
                a.download = d.filename;
                a.click();
            }
            // Revoke after a delay so the new tab can finish loading
            setTimeout(() => URL.revokeObjectURL(url), 60_000);
        } catch (e) {
            toast.error("Could not open document");
        }
    };

    const openAssign = (d) => {
        setAssignDoc(d);
        setAssignSelection(d.assigned_to || []);
    };

    const saveAssignments = async () => {
        if (!assignDoc) return;
        setAssignBusy(true);
        try {
            await api.patch(`/v2/documents/${assignDoc.id}/assignments`, {
                editor_ids: assignSelection,
            });
            toast.success("Assignments updated");
            setDocs((c) => c.map((x) => x.id === assignDoc.id ? { ...x, assigned_to: assignSelection } : x));
            setAssignDoc(null);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Update failed");
        } finally {
            setAssignBusy(false);
        }
    };

    const toggleAssignEditor = (id) => {
        setAssignSelection((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
    };

    // Distinct uploaders (for owner filter dropdown)
    const uploaderOptions = useMemo(() => {
        const map = new Map();
        for (const d of docs) {
            if (!d.owner_id) continue;
            if (!map.has(d.owner_id)) {
                map.set(d.owner_id, { id: d.owner_id, name: d.owner_name || d.owner_id });
            }
        }
        return Array.from(map.values()).sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    }, [docs]);

    const filteredDocs = useMemo(() => docs, [docs]);

    // Stream 2 — bulk assignment helpers
    const openBulkAssign = () => {
        setBulkSelection([]);
        setBulkAssignOpen(true);
    };
    const toggleBulkEditor = (id) => {
        setBulkSelection((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
    };
    const submitBulkAssign = async () => {
        if (!bulkSelection.length) { toast.error("Pick at least one editor"); return; }
        if (!selected.length) { toast.error("Pick at least one document"); return; }
        setBulkBusy(true);
        try {
            const r = await api.post("/v2/documents/bulk-assign", {
                document_ids: selected,
                editor_ids: bulkSelection,
            });
            toast.success(`Assigned ${r.data.editors.length} editor(s) to ${r.data.matched} document(s)`);
            setBulkAssignOpen(false);
            setSelected([]);
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Bulk assignment failed");
        } finally {
            setBulkBusy(false);
        }
    };

    const submitBulkKb = async () => {
        if (!selected.length) { toast.error("Pick at least one document"); return; }
        setBulkKbBusy(true);
        try {
            const target = bulkKbTarget === "__none__" ? null : bulkKbTarget;
            const r = await api.post("/v2/documents/bulk-assign-kb", {
                document_ids: selected,
                kb_id: target,
            });
            toast.success(target
                ? `Moved ${r.data.matched} doc(s) into the knowledge base`
                : `Removed ${r.data.matched} doc(s) from their knowledge base`);
            setBulkKbOpen(false);
            setSelected([]);
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Move failed");
        } finally {
            setBulkKbBusy(false);
        }
    };

    return (
        <div>
            <header className="h-auto md:h-16 border-b border-border px-4 md:px-8 py-3 md:py-0 flex flex-col md:flex-row md:items-center justify-between gap-3 sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Workspace</div>
                    <h1 className="font-heading font-bold text-lg">Documents</h1>
                </div>
                <div className="flex flex-wrap items-center gap-2 md:gap-3">
                    {selected.length > 0 && (
                        <>
                            <span className="text-sm text-muted-foreground" data-testid="selection-count">{selected.length} selected</span>
                            <Button variant="outline" onClick={chatSelected} data-testid="chat-selected-button" className="min-h-[44px] md:min-h-0">
                                <ChatCircle size={16} /> Chat with selected
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => { setBulkKbTarget("__none__"); setBulkKbOpen(true); }}
                                data-testid="bulk-kb-button"
                                className="min-h-[44px] md:min-h-0"
                            >
                                <BookOpen size={16} /> Move to KB
                            </Button>
                            {isOwner && (
                                <Button
                                    variant="outline"
                                    onClick={openBulkAssign}
                                    data-testid="bulk-assign-button"
                                    className="min-h-[44px] md:min-h-0"
                                >
                                    <UserPlus size={16} /> Assign selected
                                </Button>
                            )}
                        </>
                    )}
                    <Button onClick={() => setUploadOpen(true)} data-testid="upload-open-button" className="min-h-[44px] md:min-h-0">
                        <Plus size={16} /> Upload
                    </Button>
                </div>
            </header>

            <div className="p-4 sm:p-6 md:p-8 max-w-7xl">
                <div className="flex flex-col sm:flex-row sm:items-end gap-3 mb-4 flex-wrap" data-testid="document-filters">
                    <div className="flex-1 min-w-[220px] sm:max-w-md">
                        <Label className="dc-overline" htmlFor="document-search-input">Search</Label>
                        {/* Stream 5 — search icon vertical alignment.
                            Icon lives in its OWN relative wrapper around the input,
                            so top-1/2 -translate-y-1/2 tracks the input's center at
                            every breakpoint, independent of the label height. */}
                        <div className="relative mt-1">
                            <MagnifyingGlass
                                size={16}
                                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                            />
                            <Input
                                id="document-search-input"
                                placeholder="Document name, tag, or uploader…"
                                className="pl-9 h-9 w-full"
                                value={q}
                                onChange={(e) => setQ(e.target.value)}
                                data-testid="document-search-input"
                            />
                        </div>
                    </div>
                    {/* Stream 1 — category filter (visible to everyone) */}
                    <div className="w-full sm:w-[170px]">
                        <Label className="dc-overline">Category</Label>
                        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                            <SelectTrigger className="mt-1 h-9" data-testid="document-filter-category">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="Uncategorized">Uncategorized</SelectItem>
                                {DOCUMENT_CATEGORIES.map((c) => (
                                    <SelectItem key={c} value={c}>{c}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    {/* Mar 2026 — KB scope filter */}
                    <div className="w-full sm:w-[180px]">
                        <Label className="dc-overline">Knowledge Base</Label>
                        <Select value={kbFilter} onValueChange={setKbFilter}>
                            <SelectTrigger className="mt-1 h-9" data-testid="document-filter-kb">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="none">No KB (unassigned)</SelectItem>
                                {knowledgeBases.map((kb) => (
                                    <SelectItem key={kb.id} value={kb.id}>{kb.name}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    {isOwner && (
                        <div className="w-full sm:w-[170px]">
                            <Label className="dc-overline">Uploaded by</Label>
                            <Select value={uploaderFilter} onValueChange={setUploaderFilter}>
                                <SelectTrigger className="mt-1 h-9" data-testid="document-filter-uploader">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All</SelectItem>
                                    <SelectItem value="self">Me</SelectItem>
                                    {uploaderOptions.map((u) => (
                                        <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}
                    <div className="w-full sm:w-[160px]">
                        <Label className="dc-overline">Access</Label>
                        <Select value={accessFilter} onValueChange={setAccessFilter}>
                            <SelectTrigger className="mt-1 h-9" data-testid="document-filter-access">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="self">Uploaded by self</SelectItem>
                                <SelectItem value="assigned">Assigned to me</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="w-full sm:w-[140px]">
                        <Label className="dc-overline">Status</Label>
                        <Select value={statusFilter} onValueChange={setStatusFilter}>
                            <SelectTrigger className="mt-1 h-9" data-testid="document-filter-status">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All</SelectItem>
                                <SelectItem value="ready">Ready</SelectItem>
                                <SelectItem value="processing">Processing</SelectItem>
                                <SelectItem value="failed">Failed</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <Link to="/app/chat" className="sm:ml-auto">
                        <Button variant="ghost" data-testid="chat-all-button" className="min-h-[44px] md:min-h-0 w-full sm:w-auto">
                            <ChatCircle size={16} /> Chat with all
                        </Button>
                    </Link>
                </div>

                {loading && <div className="text-sm text-muted-foreground">Loading documents…</div>}

                {!loading && docs.length === 0 && (
                    <div className="border border-dashed border-border p-16 text-center" data-testid="empty-documents">
                        <FileText size={40} weight="duotone" className="mx-auto text-muted-foreground" />
                        <h2 className="font-heading font-bold text-xl mt-4">No documents yet</h2>
                        <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
                            Upload a PDF, DOCX, PPTX, XLSX, CSV, image, or text file to start chatting with it.
                        </p>
                        <Button className="mt-6" onClick={() => setUploadOpen(true)} data-testid="empty-upload-button">
                            <Plus size={16} /> Upload document
                        </Button>
                    </div>
                )}

                {!loading && docs.length > 0 && filteredDocs.length === 0 && (
                    <div className="border border-dashed border-border p-12 text-center text-sm text-muted-foreground" data-testid="document-no-match">
                        No documents match the current filters.
                    </div>
                )}

                {!loading && filteredDocs.length > 0 && (
                    <div className="border border-border overflow-x-auto">
                        {/* Stream 1 + Stream 7 — category column added; lg+ shows full grid,
                            md collapses Tags/Size; sm becomes a stacked card. */}
                        <div className="hidden lg:grid grid-cols-[36px_1fr_140px_180px_110px_100px_80px_140px] gap-4 px-4 py-3 bg-secondary/50 border-b border-border text-xs font-mono uppercase tracking-wider text-muted-foreground min-w-[1000px]">
                            <div></div>
                            <div>File</div>
                            <div>Category</div>
                            <div>Status</div>
                            <div>Pages / Chunks</div>
                            <div>Tags</div>
                            <div>Size</div>
                            <div className="text-right">Actions</div>
                        </div>
                        {filteredDocs.map((d) => (
                            <div
                                key={d.id}
                                className="grid grid-cols-[36px_1fr] sm:grid-cols-[36px_1fr_140px] md:grid-cols-[36px_1fr_140px_180px] lg:grid-cols-[36px_1fr_140px_180px_110px_100px_80px_140px] gap-2 sm:gap-4 px-3 sm:px-4 py-3 border-b border-border last:border-b-0 hover:bg-secondary/30 transition-colors items-center min-w-0 lg:min-w-[1000px]"
                                data-testid={`document-row-${d.id}`}
                            >
                                <input
                                    type="checkbox"
                                    checked={selected.includes(d.id)}
                                    onChange={() => toggle(d.id)}
                                    className="w-5 h-5 sm:w-4 sm:h-4 accent-brand-primary cursor-pointer"
                                    disabled={d.status !== "ready"}
                                    data-testid={`document-checkbox-${d.id}`}
                                />
                                <div className="flex items-center gap-3 min-w-0">
                                    <IconForFile filename={d.filename} />
                                    <div className="min-w-0">
                                        <div className="font-medium truncate">{d.filename}</div>
                                        <div className="text-xs text-muted-foreground flex flex-wrap gap-x-2">
                                            <span>{new Date(d.created_at).toLocaleDateString()}</span>
                                            {d.owner_name && (
                                                <span data-testid={`document-uploader-${d.id}`}>
                                                    · by {d.owner_id === currentUser?.id ? "you" : d.owner_name}
                                                </span>
                                            )}
                                            {(d.assigned_to || []).includes(currentUser?.id) && d.owner_id !== currentUser?.id && (
                                                <span className="font-mono text-[10px] uppercase text-brand-primary">assigned</span>
                                            )}
                                            {/* Stream 7 — show status inline on small screens where the column hides */}
                                            <span className="sm:hidden">· <StatusBadge status={d.status} /></span>
                                        </div>
                                    </div>
                                </div>
                                {/* Stream 1 — Category badge (sm+ visible) */}
                                <div className="hidden sm:block">
                                    <Badge
                                        variant="outline"
                                        className="text-[10px] font-mono uppercase"
                                        data-testid={`document-category-${d.id}`}
                                    >
                                        {d.category || "Uncategorized"}
                                    </Badge>
                                </div>
                                <div className="hidden md:flex items-center gap-2 min-w-0">
                                    <div>
                                        <StatusBadge status={d.status} />
                                        {d.status !== "ready" && d.status !== "failed" && (
                                            <Progress value={d.progress || 0} className="h-1 mt-1 w-28" />
                                        )}
                                        {d.status === "failed" && d.error && (
                                            <div className="text-[10px] text-confidence-low mt-0.5 truncate max-w-[180px]" title={d.error}>
                                                {d.error.length > 50 ? d.error.slice(0, 50) + "…" : d.error}
                                            </div>
                                        )}
                                    </div>
                                    {d.status === "failed" && (
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="h-7 w-7 shrink-0"
                                            onClick={() => retry(d)}
                                            title="Retry ingestion"
                                        >
                                            <ArrowClockwise size={14} className="text-confidence-medium" />
                                        </Button>
                                    )}
                                </div>
                                <div className="hidden lg:block text-sm font-mono">
                                    {d.page_count || 0} / {d.chunk_count || 0}
                                </div>
                                <div className="hidden lg:flex flex-wrap gap-1">
                                    {(d.tags || []).slice(0, 2).map((t) => (
                                        <Badge key={t} variant="outline" className="text-[10px] font-mono uppercase">{t}</Badge>
                                    ))}
                                </div>
                                <div className="hidden lg:block text-xs font-mono text-muted-foreground">{(d.size / 1024).toFixed(0)}KB</div>
                                <div className="col-span-2 sm:col-span-1 flex items-center justify-end gap-1 flex-wrap">
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-9 sm:h-8 min-h-[44px] sm:min-h-0 px-2 gap-1 text-xs"
                                        onClick={() => viewDocument(d)}
                                        data-testid={`document-view-${d.id}`}
                                        title="View document"
                                    >
                                        <Eye size={14} /> View
                                    </Button>
                                    {isOwner && (
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-11 w-11 sm:h-8 sm:w-8"
                                            onClick={() => openAssign(d)}
                                            data-testid={`document-assign-${d.id}`}
                                            title="Assign to editors"
                                        >
                                            <UserPlus size={15} />
                                        </Button>
                                    )}
                                    <Button variant="ghost" size="icon" className="h-11 w-11 sm:h-8 sm:w-8" onClick={() => del(d)} data-testid={`document-delete-${d.id}`} title="Delete">
                                        <Trash size={15} />
                                    </Button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} onUploaded={load} />

            {/* Mar 2026 — Bulk move-to-KB dialog (any role can move their own docs). */}
            <Dialog open={bulkKbOpen} onOpenChange={setBulkKbOpen}>
                <DialogContent data-testid="bulk-kb-dialog" className="w-[calc(100vw-1.5rem)] max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">Move {selected.length} document(s) to a knowledge base</DialogTitle>
                        <DialogDescription>
                            Pick the target KB or "No KB" to remove the association.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 mt-1">
                        <Label className="dc-overline">Knowledge Base</Label>
                        <Select value={bulkKbTarget} onValueChange={setBulkKbTarget}>
                            <SelectTrigger className="h-9" data-testid="bulk-kb-target"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">No KB (unassign)</SelectItem>
                                {knowledgeBases.map(kb => (
                                    <SelectItem key={kb.id} value={kb.id}>{kb.name}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {knowledgeBases.length === 0 && (
                            <div className="text-xs text-muted-foreground">No knowledge bases yet — create one from the Knowledge Bases page.</div>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setBulkKbOpen(false)} disabled={bulkKbBusy}>Cancel</Button>
                        <Button onClick={submitBulkKb} disabled={bulkKbBusy} data-testid="bulk-kb-submit">
                            {bulkKbBusy ? "Moving…" : "Move"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Stream 2 — Bulk assign dialog (admin only). Reuses the editors list. */}
            <Dialog open={bulkAssignOpen} onOpenChange={setBulkAssignOpen}>
                <DialogContent data-testid="bulk-assign-dialog" className="w-[calc(100vw-1.5rem)] max-w-md sm:max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">Assign {selected.length} document(s)</DialogTitle>
                        <DialogDescription>
                            Select one or more editors. Existing assignments are preserved (no duplicates).
                        </DialogDescription>
                    </DialogHeader>
                    <div className="border border-border max-h-72 overflow-auto">
                        {editors.length === 0 && (
                            <div className="p-4 text-sm text-muted-foreground">No editors yet. Create one from Admin → Users.</div>
                        )}
                        {editors.map((ed) => (
                            <label
                                key={ed.id}
                                className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-b-0 cursor-pointer hover:bg-secondary/30"
                                data-testid={`bulk-assign-editor-${ed.id}`}
                            >
                                <input
                                    type="checkbox"
                                    checked={bulkSelection.includes(ed.id)}
                                    onChange={() => toggleBulkEditor(ed.id)}
                                    className="w-4 h-4 accent-brand-primary"
                                />
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium">{ed.name}</div>
                                    <div className="text-xs font-mono text-muted-foreground truncate">{ed.email}</div>
                                </div>
                            </label>
                        ))}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setBulkAssignOpen(false)}>Cancel</Button>
                        <Button onClick={submitBulkAssign} disabled={bulkBusy || !bulkSelection.length} data-testid="bulk-assign-submit-button">
                            {bulkBusy ? "Assigning…" : `Assign to ${bulkSelection.length} editor(s)`}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={!!assignDoc} onOpenChange={(o) => !o && setAssignDoc(null)}>
                <DialogContent data-testid="assign-dialog" className="w-[calc(100vw-1.5rem)] max-w-md sm:max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">Assign editors</DialogTitle>
                        <DialogDescription>
                            Choose which editors should see <span className="font-mono">{assignDoc?.filename}</span>. Editors keep access to their own uploads regardless.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="border border-border max-h-72 overflow-auto">
                        {editors.length === 0 && (
                            <div className="p-4 text-sm text-muted-foreground">No editors yet. Create one from Admin → Users.</div>
                        )}
                        {editors.map((ed) => (
                            <label
                                key={ed.id}
                                className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-b-0 cursor-pointer hover:bg-secondary/30"
                                data-testid={`assign-editor-${ed.id}`}
                            >
                                <input
                                    type="checkbox"
                                    checked={assignSelection.includes(ed.id)}
                                    onChange={() => toggleAssignEditor(ed.id)}
                                    className="w-4 h-4 accent-brand-primary"
                                />
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium">{ed.name}</div>
                                    <div className="text-xs font-mono text-muted-foreground truncate">{ed.email}</div>
                                </div>
                            </label>
                        ))}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setAssignDoc(null)}>Cancel</Button>
                        <Button onClick={saveAssignments} disabled={assignBusy} data-testid="assign-save-button">
                            {assignBusy ? "Saving…" : "Save"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
