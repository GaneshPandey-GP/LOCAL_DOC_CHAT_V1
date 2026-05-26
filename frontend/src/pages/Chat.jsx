import React, { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams, useNavigate, Link } from "react-router-dom";
import api, { API_BASE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import MarkdownMessage from "@/components/MarkdownMessage";
import { toast } from "sonner";
import {
    PaperPlaneRight,
    ThumbsUp,
    ThumbsDown,
    Copy,
    Plus,
    ChatCircle,
    Trash,
    PencilSimple,
    FileText,
    Lightning,
} from "@phosphor-icons/react";

function SessionList({ current, onPick, refreshKey, onDeleted }) {
    const [sessions, setSessions] = useState([]);
    useEffect(() => {
        api.get("/v2/sessions").then((r) => setSessions(r.data)).catch(() => {});
    }, [refreshKey]);

    const rename = async (s) => {
        const t = window.prompt("Rename session", s.title);
        if (!t) return;
        await api.patch(`/v2/sessions/${s.id}`, { title: t });
        setSessions((c) => c.map((x) => (x.id === s.id ? { ...x, title: t } : x)));
    };
    const del = async (s) => {
        if (!window.confirm(`Delete "${s.title}"?`)) return;
        await api.delete(`/v2/sessions/${s.id}`);
        setSessions((c) => c.filter((x) => x.id !== s.id));
        onDeleted?.(s.id);
    };

    return (
        /*
         * PANEL 2 — SESSION LIST
         * h-full fills the grid cell (which is 100vh via AppLayout's h-screen grid).
         * The header ("New chat" button) is flex-shrink-0 — never moves.
         * Only the inner <div> (the list) gets overflow-auto and scrolls.
         */
        <div className="h-full flex flex-col overflow-hidden">
            {/* Panel 2 header — fixed, never scrolls */}
            <div className="p-3 border-b border-border flex-shrink-0">
                <Link to="/app/chat">
                    <Button variant="outline" className="w-full justify-start h-10" data-testid="new-chat-button">
                        <Plus size={16} /> New chat
                    </Button>
                </Link>
            </div>

            {/*
             * FIX: only THIS div scrolls for Panel 2.
             * min-h-0 is critical — without it a flex child won't shrink
             * below its content size and overflow-auto won't trigger.
             */}
            <div className="flex-1 overflow-y-auto min-h-0">
                {sessions.length === 0 && (
                    <div className="p-4 text-xs text-muted-foreground">No sessions yet.</div>
                )}
                {sessions.map((s) => (
                    <div
                        key={s.id}
                        className={`group flex items-center gap-2 px-3 py-2.5 border-l-2 cursor-pointer transition-colors ${
                            current === s.id ? "border-brand-primary bg-secondary" : "border-transparent hover:bg-secondary/50"
                        }`}
                        onClick={() => onPick(s.id)}
                        data-testid={`session-row-${s.id}`}
                    >
                        <ChatCircle size={16} className="text-muted-foreground shrink-0" />
                        <div className="min-w-0 flex-1">
                            <div className="text-sm truncate">{s.title}</div>
                            <div className="text-[11px] text-muted-foreground font-mono">
                                {new Date(s.updated_at).toLocaleDateString()}
                            </div>
                        </div>
                        <div className="hidden group-hover:flex gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); rename(s); }} data-testid={`session-rename-${s.id}`}>
                                <PencilSimple size={13} />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); del(s); }} data-testid={`session-delete-${s.id}`}>
                                <Trash size={13} />
                            </Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function CitationPanel({ citation, onClose }) {
    return (
        <Dialog open={!!citation} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="citation-panel" className="w-[calc(100vw-1.5rem)] max-w-md sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle className="font-heading">{citation?.filename}</DialogTitle>
                    <DialogDescription>Page {citation?.page} · Source [{citation?.index}]</DialogDescription>
                </DialogHeader>
                <div className="border border-border p-4 bg-secondary/50 font-mono text-[13px] leading-relaxed whitespace-pre-wrap">
                    {citation?.text}
                </div>
            </DialogContent>
        </Dialog>
    );
}

export default function Chat() {
    const { sessionId: routeSessionId } = useParams();
    const [searchParams] = useSearchParams();
    const nav = useNavigate();

    const [sessionId, setSessionId] = useState(routeSessionId || null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [streaming, setStreaming] = useState(false);
    const [docIds, setDocIds] = useState(() => {
        const d = searchParams.get("docs");
        return d ? d.split(",") : null;
    });
    const [activeCite, setActiveCite] = useState(null);
    const [sessionsRefresh, setSessionsRefresh] = useState(0);
    const [followups, setFollowups] = useState([]);
    const [feedbackMap, setFeedbackMap] = useState({});
    const [docCount, setDocCount] = useState(0);
    const [mcpTools, setMcpTools] = useState([]);
    const [selectedToolIds, setSelectedToolIds] = useState([]);
    const [toolsOpen, setToolsOpen] = useState(false);
    const bottomRef = useRef(null);

    useEffect(() => {
        api.get("/v2/documents").then((r) => setDocCount(r.data.filter((d) => d.status === "ready").length)).catch(() => {});
        api.get("/v2/mcp/tools").then(r => setMcpTools((r.data || []).filter(t => t.enabled !== false))).catch(() => {});
    }, []);

    useEffect(() => {
        setSessionId(routeSessionId || null);
        if (routeSessionId) {
            api.get(`/v2/sessions/${routeSessionId}/messages`).then((r) => {
                setMessages(r.data.messages || []);
                const scope = r.data?.session?.scope_doc_ids;
                if (Array.isArray(scope)) {
                    setDocIds(scope.length > 0 ? scope : []);
                } else if (scope === null || scope === undefined) {
                    setDocIds(null);
                }
            }).catch(() => nav("/app/chat"));
        } else {
            setMessages([]);
            const d = searchParams.get("docs");
            setDocIds(d ? d.split(",") : null);
        }
        setFollowups([]);
    }, [routeSessionId, nav, searchParams]);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streaming]);

    const send = async (textOverride) => {
        const text = (textOverride ?? input).trim();
        if (!text || streaming) return;
        setInput("");
        setFollowups([]);

        const userMsg = { id: `u-${Date.now()}`, role: "user", content: text };
        setMessages((m) => [...m, userMsg]);

        const assistantDraft = { id: `a-${Date.now()}`, role: "assistant", content: "", citations: [], confidence: null, tool_calls: [], streaming: true };
        setMessages((m) => [...m, assistantDraft]);
        setStreaming(true);

        try {
            const token = localStorage.getItem("dc_access_token");
            const body = {
                query: text,
                session_id: sessionId,
                document_ids: docIds,
                stream: true,
            };
            if (selectedToolIds.length) body.mcp_tool_ids = selectedToolIds;
            const resp = await fetch(`${API_BASE}/v2/chat`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(body),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || "Chat failed");
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let newSessionId = sessionId;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split("\n\n");
                buffer = events.pop() || "";
                for (const ev of events) {
                    const lines = ev.split("\n");
                    let eventType = "message";
                    let data = "";
                    for (const line of lines) {
                        if (line.startsWith("event:")) eventType = line.slice(6).trim();
                        else if (line.startsWith("data:")) data += line.slice(5).trim();
                    }
                    if (!data) continue;
                    try {
                        const payload = JSON.parse(data);
                        if (eventType === "meta") {
                            newSessionId = payload.session_id;
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, citations: payload.citations, confidence: payload.confidence }
                                : mm));
                        } else if (eventType === "tool_calls") {
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, tool_calls: payload.tool_calls || [] }
                                : mm));
                        } else if (eventType === "token") {
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, content: (mm.content || "") + payload.t }
                                : mm));
                        } else if (eventType === "done") {
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, id: payload.message_id, streaming: false }
                                : mm));
                            setFollowups(payload.followups || []);
                        }
                    } catch {}
                }
            }

            if (!sessionId && newSessionId) {
                setSessionId(newSessionId);
                nav(`/app/chat/${newSessionId}`, { replace: true });
            }
            setSessionsRefresh((x) => x + 1);
        } catch (e) {
            toast.error(e.message || "Chat failed");
            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                ? { ...mm, content: `_Error: ${e.message}_`, streaming: false }
                : mm));
        } finally {
            setStreaming(false);
        }
    };

    const submitFeedback = async (msgId, rating) => {
        try {
            await api.post("/v2/feedback", { message_id: msgId, rating });
            setFeedbackMap((m) => ({ ...m, [msgId]: rating }));
            toast.success("Thanks for the feedback");
        } catch (e) {
            toast.error("Could not submit feedback");
        }
    };

    const copyMsg = (content) => {
        navigator.clipboard.writeText(content);
        toast.success("Copied to clipboard");
    };

    const pickSession = (id) => nav(`/app/chat/${id}`);

    return (
        /*
         * PANEL 2 + PANEL 3 container.
         *
         * FIX 1: h-screen  →  h-full
         *   Chat lives inside AppLayout's <main className="overflow-hidden min-h-0">.
         *   AppLayout's root is already h-screen, so h-full here means
         *   "fill the 100vh cell AppLayout gave me" — no double viewport stacking.
         *   Using h-screen inside an overflow-hidden parent created a second
         *   100vh context that escaped containment.
         */
        <div className="h-full md:grid md:grid-cols-[260px_1fr] flex flex-col overflow-hidden">

            {/*
             * PANEL 2 — SESSION LIST SIDEBAR
             * Hidden on mobile (md+); chat takes full width. Users still reach
             * sessions via the main app sidebar drawer (AppLayout) on small.
             */}
            <aside className="hidden md:block border-r border-border overflow-hidden">
                <SessionList
                    current={sessionId}
                    onPick={pickSession}
                    refreshKey={sessionsRefresh}
                    onDeleted={(id) => { if (id === sessionId) nav("/app/chat"); }}
                />
            </aside>

            {/*
             * PANEL 3 — MAIN CHAT COLUMN
             *
             * FIX 2: h-screen  →  h-full
             *   Same reason as above — h-full fills the grid cell correctly.
             *   overflow-hidden ensures nothing leaks out of this column.
             */}
            <div className="flex flex-col h-full overflow-hidden flex-1 min-h-0">

                {/* Panel 3 header — flex-shrink-0, always visible, never scrolls */}
                <header className="h-14 md:h-16 border-b border-border px-4 md:px-6 flex items-center justify-between flex-shrink-0">
                    <div className="flex items-center gap-2 md:gap-3">
                        <ChatCircle size={22} weight="duotone" className="text-brand-primary" />
                        <div>
                            <div className="dc-overline">Chat</div>
                            <div className="font-heading font-bold text-base md:text-lg">
                                {docIds?.length ? `Scoped · ${docIds.length} docs` : `All documents · ${docCount} ready`}
                            </div>
                        </div>
                    </div>
                </header>

                {/*
                 * ✅ ONLY THIS DIV SCROLLS for Panel 3.
                 * flex-1 takes all remaining vertical space between header and input bar.
                 * overflow-y-auto scrolls when content overflows.
                 * min-h-0 lets flex shrink it below its content size.
                 * Scrolling here does NOT affect Panel 1 or Panel 2.
                 */}
                <div className="flex-1 overflow-y-auto min-h-0 px-3 sm:px-6 md:px-10 py-4 md:py-8">
                    <div className="max-w-3xl mx-auto space-y-6">
                        {messages.length === 0 && (
                            <div className="text-center py-16" data-testid="chat-empty-state">
                                <Lightning size={36} weight="duotone" className="mx-auto text-brand-primary" />
                                <h2 className="font-heading font-bold text-2xl mt-4">Ask anything about your documents</h2>
                                <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
                                    Responses are grounded in your documents with inline citations and confidence scoring.
                                </p>
                                <div className="grid sm:grid-cols-2 gap-3 mt-8 max-w-2xl mx-auto">
                                    {[
                                        "Summarize the key points",
                                        "What are the main risks mentioned?",
                                        "Extract all dates and deadlines",
                                        "Compare the main arguments",
                                    ].map((s, i) => (
                                        <button
                                            key={i}
                                            onClick={() => send(s)}
                                            className="border border-border p-4 text-left text-sm hover:border-brand-primary hover:bg-secondary/50 transition-colors"
                                            data-testid={`suggestion-${i}`}
                                        >
                                            {s}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {messages.map((m) => (
                            <div key={m.id} className="animate-fade-in" data-testid={`message-${m.role}`}>
                                {m.role === "user" ? (
                                    <div className="flex justify-end">
                                        <div className="bg-secondary border border-border px-4 py-3 rounded-sm max-w-[90%] sm:max-w-[80%] text-[15px] break-words">
                                            {m.content}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="border-l-2 border-brand-primary pl-3 sm:pl-5 max-w-full">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className="dc-overline">DocChat</div>
                                            {m.confidence && <ConfidenceBadge level={m.confidence} />}
                                            {(m.citations?.length ?? 0) > 0 && (
                                                <span className="text-xs text-muted-foreground font-mono">
                                                    {m.citations.length} source{m.citations.length === 1 ? "" : "s"}
                                                </span>
                                            )}
                                        </div>
                                        {(m.tool_calls?.length || 0) > 0 && (
                                            <details className="mb-3 border border-border bg-secondary/30" data-testid={`tool-calls-${m.id}`}>
                                                <summary className="px-3 py-1.5 text-xs font-mono cursor-pointer select-none">⚙ {m.tool_calls.length} tool{m.tool_calls.length > 1 ? "s" : ""} used</summary>
                                                <div className="px-3 py-2 space-y-2">
                                                    {m.tool_calls.map((tc, i) => (
                                                        <div key={i} className="text-xs font-mono border-t border-border pt-1.5 first:border-t-0 first:pt-0">
                                                            <div className="flex items-center justify-between flex-wrap gap-2">
                                                                <span className="font-bold">{tc.tool_name}</span>
                                                                <span className="text-muted-foreground">{tc.elapsed_ms || 0}ms</span>
                                                            </div>
                                                            <div className="text-muted-foreground truncate">in: {typeof tc.input === "string" ? tc.input : JSON.stringify(tc.input)}</div>
                                                            <div className="text-muted-foreground truncate">out: {tc.result_preview || (typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result))?.slice(0, 200)}</div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </details>
                                        )}
                                        <MarkdownMessage content={m.content} citations={m.citations || []} onCite={setActiveCite} />
                                        {m.streaming && <span className="dc-cursor" />}

                                        {!m.streaming && m.content && (
                                            <div className="mt-3 flex items-center gap-1">
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    className={`h-8 w-8 ${feedbackMap[m.id] === 1 ? "text-confidence-high" : ""}`}
                                                    onClick={() => submitFeedback(m.id, 1)}
                                                    data-testid={`feedback-up-${m.id}`}
                                                >
                                                    <ThumbsUp size={14} weight={feedbackMap[m.id] === 1 ? "fill" : "regular"} />
                                                </Button>
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    className={`h-8 w-8 ${feedbackMap[m.id] === -1 ? "text-confidence-low" : ""}`}
                                                    onClick={() => submitFeedback(m.id, -1)}
                                                    data-testid={`feedback-down-${m.id}`}
                                                >
                                                    <ThumbsDown size={14} weight={feedbackMap[m.id] === -1 ? "fill" : "regular"} />
                                                </Button>
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    className="h-8 w-8"
                                                    onClick={() => copyMsg(m.content)}
                                                    data-testid={`copy-message-${m.id}`}
                                                >
                                                    <Copy size={14} />
                                                </Button>
                                            </div>
                                        )}

                                        {m.citations?.length > 0 && !m.streaming && (
                                            <div className="mt-4 space-y-1 text-xs">
                                                <div className="dc-overline mb-2">Sources</div>
                                                {m.citations.map((c) => (
                                                    <button
                                                        key={c.chunk_id}
                                                        onClick={() => setActiveCite(c)}
                                                        className="flex items-center gap-2 text-left w-full py-1.5 px-2 hover:bg-secondary/50 border border-border rounded-sm transition-colors"
                                                        data-testid={`source-${c.index}`}
                                                    >
                                                        <span className="font-mono text-[11px] bg-secondary border border-border px-1.5 py-0.5 rounded-sm">[{c.index}]</span>
                                                        <FileText size={13} className="text-muted-foreground" />
                                                        <span className="truncate flex-1">{c.filename}</span>
                                                        <span className="text-muted-foreground font-mono">p.{c.page}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}

                        {followups.length > 0 && !streaming && (
                            <div className="ml-5" data-testid="followup-suggestions">
                                <div className="dc-overline mb-2">Follow-ups</div>
                                <div className="flex flex-wrap gap-2">
                                    {followups.map((f, i) => (
                                        <button
                                            key={i}
                                            onClick={() => send(f)}
                                            className="text-sm border border-border px-3 py-1.5 hover:border-brand-primary hover:bg-secondary/50 transition-colors"
                                            data-testid={`followup-${i}`}
                                        >
                                            {f}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div ref={bottomRef} />
                    </div>
                </div>

                {/* Input bar — flex-shrink-0, always pinned to bottom of Panel 3 */}
                <div className="border-t border-border p-3 md:p-4 flex-shrink-0">
                    <form
                        onSubmit={(e) => { e.preventDefault(); send(); }}
                        className="max-w-3xl mx-auto flex items-end gap-2"
                        data-testid="chat-form"
                    >
                        <Textarea
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                    e.preventDefault();
                                    send();
                                }
                            }}
                            placeholder={docCount === 0 ? "Upload a document first…" : "Ask about your documents…"}
                            rows={2}
                            disabled={streaming || docCount === 0}
                            className="resize-none font-sans"
                            data-testid="chat-input"
                        />
                        <div className="flex flex-col gap-1.5 items-stretch">
                            {mcpTools.length > 0 && (
                                <div className="relative">
                                    <Button type="button" size="sm" variant={selectedToolIds.length ? "default" : "outline"}
                                        className="h-8 text-xs px-2.5" onClick={() => setToolsOpen(o => !o)} data-testid="chat-tools-toggle">
                                        ⚙ Tools{selectedToolIds.length ? ` (${selectedToolIds.length})` : ""}
                                    </Button>
                                    {toolsOpen && (
                                        <div className="absolute bottom-10 right-0 w-72 max-h-72 overflow-auto border border-border bg-background shadow-xl z-30 p-2" data-testid="chat-tools-popover">
                                            <div className="dc-overline mb-2">Available MCP Tools</div>
                                            {mcpTools.map(t => (
                                                <label key={t.id} className="flex items-center gap-2 px-1 py-1.5 hover:bg-secondary/50 cursor-pointer text-sm">
                                                    <input type="checkbox" className="w-4 h-4 accent-brand-primary"
                                                        checked={selectedToolIds.includes(t.id)}
                                                        onChange={() => setSelectedToolIds(s => s.includes(t.id) ? s.filter(x => x !== t.id) : [...s, t.id])}
                                                        data-testid={`chat-tool-${t.id}`} />
                                                    <span className="truncate flex-1">{t.name}</span>
                                                    <span className="text-[10px] font-mono text-muted-foreground">{t.is_builtin ? "built-in" : "custom"}</span>
                                                </label>
                                            ))}
                                            <div className="flex justify-end gap-2 pt-2 border-t border-border mt-2">
                                                <button type="button" className="text-[11px] text-muted-foreground hover:underline" onClick={() => setSelectedToolIds([])}>Clear</button>
                                                <button type="button" className="text-[11px] text-brand-primary hover:underline" onClick={() => setToolsOpen(false)}>Done</button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                            <Button type="submit" disabled={streaming || !input.trim() || docCount === 0} className="h-11 min-w-[44px]" data-testid="chat-send-button">
                                <PaperPlaneRight size={16} weight="fill" />
                            </Button>
                        </div>
                    </form>
                </div>
            </div>

            <CitationPanel citation={activeCite} onClose={() => setActiveCite(null)} />
        </div>
    );
}

