import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, ShieldCheck, Lightning, Chats, Database, Lock, Graph } from "@phosphor-icons/react";

function Feature({ icon: Icon, title, desc, idx }) {
    return (
        <div className="dc-card p-6 dc-card-hover" data-testid={`feature-card-${idx}`}>
            <Icon size={28} weight="duotone" className="text-brand-primary" />
            <h3 className="font-heading text-xl font-bold mt-4">{title}</h3>
            <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{desc}</p>
        </div>
    );
}

export default function Landing() {
    return (
        <div className="min-h-screen">
            {/* Header */}
            <header className="border-b border-border bg-background sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-6 md:px-10 h-16 flex items-center justify-between">
                    <Link to="/" className="flex items-center gap-2" data-testid="brand-logo">
                        <div className="w-7 h-7 bg-brand-primary grid place-items-center">
                            <span className="text-white font-heading font-black text-sm">D</span>
                        </div>
                        <span className="font-heading font-bold text-lg">DocChat</span>
                    </Link>
                    <nav className="hidden md:flex items-center gap-8 text-sm">
                        <a href="#features" className="hover:text-brand-primary" data-testid="nav-features">Features</a>
                        <a href="#security" className="hover:text-brand-primary" data-testid="nav-security">Security</a>
                        <a href="#pricing" className="hover:text-brand-primary" data-testid="nav-pricing">Pricing</a>
                    </nav>
                    <div className="flex items-center gap-2">
                        <Link to="/login"><Button variant="ghost" size="sm" data-testid="header-login-button">Sign in</Button></Link>
                        <Link to="/register"><Button size="sm" data-testid="header-register-button">Start free</Button></Link>
                    </div>
                </div>
            </header>

            {/* Hero */}
            <section className="border-b border-border relative overflow-hidden">
                <div className="max-w-7xl mx-auto px-6 md:px-10 py-20 md:py-32 grid md:grid-cols-12 gap-8">
                    <div className="md:col-span-7">
                        <div className="dc-overline mb-6">v2.0 · Enterprise RAG Platform</div>
                        <h1 className="font-heading font-black text-5xl md:text-6xl lg:text-7xl tracking-tighter leading-[0.95]">
                            Conversations<br />
                            grounded in<br />
                            <span className="text-brand-primary">your documents.</span>
                        </h1>
                        <p className="mt-8 text-lg text-muted-foreground max-w-xl leading-relaxed">
                            Upload documents. Ask anything. Get answers with inline citations, confidence scoring,
                            and zero hallucinations. Share securely with tokenized links scoped to exact document sets.
                        </p>
                        <div className="mt-10 flex flex-wrap gap-3">
                            <Link to="/register">
                                <Button size="lg" className="h-12 px-6" data-testid="hero-cta-primary">
                                    Start building <ArrowRight size={18} className="ml-1" />
                                </Button>
                            </Link>
                            <Link to="/login">
                                <Button size="lg" variant="outline" className="h-12 px-6" data-testid="hero-cta-secondary">
                                    Sign in
                                </Button>
                            </Link>
                        </div>
                        <div className="mt-10 flex flex-wrap gap-6 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1.5"><ShieldCheck size={14} weight="fill" /> SOC 2 ready architecture</span>
                            <span className="flex items-center gap-1.5"><Lock size={14} weight="fill" /> JWT + RBAC + audit log</span>
                            <span className="flex items-center gap-1.5"><Lightning size={14} weight="fill" /> Streaming responses</span>
                        </div>
                    </div>
                    <div className="md:col-span-5 relative">
                        <div className="aspect-[4/5] border border-border bg-secondary relative overflow-hidden dc-grid">
                            <img
                                src="https://images.pexels.com/photos/27077489/pexels-photo-27077489.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
                                alt=""
                                className="w-full h-full object-cover grayscale"
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-background/80 to-transparent" />
                            <div className="absolute bottom-0 left-0 right-0 p-6 border-t border-border bg-card">
                                <div className="dc-overline">system.status</div>
                                <div className="font-mono text-sm mt-2 flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-confidence-high animate-pulse" />
                                    All services operational
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features */}
            <section id="features" className="border-b border-border py-20">
                <div className="max-w-7xl mx-auto px-6 md:px-10">
                    <div className="max-w-2xl">
                        <div className="dc-overline mb-4">Platform</div>
                        <h2 className="font-heading font-black text-4xl md:text-5xl tracking-tighter">
                            Built for serious document work.
                        </h2>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-0 mt-12 border-l border-t border-border">
                        {[
                            { icon: Chats, title: "Streaming answers with citations", desc: "Token-by-token responses with inline [1][2] citations you can click to preview the exact source passage." },
                            { icon: ShieldCheck, title: "Role-based access control", desc: "Owner, Editor, Viewer, and Guest roles enforced on every route. No UI-only gating." },
                            { icon: Lock, title: "Secure share links", desc: "Tokenized URLs scoped server-side to an exact document subset. Password, expiry, single-use, domain-gated." },
                            { icon: Database, title: "Vector + metadata search", desc: "ChromaDB with OpenAI embeddings. Filter by tags, owner, and date. Strict document scoping enforced at query time." },
                            { icon: Lightning, title: "Confidence scoring", desc: "Every answer shows HIGH / MEDIUM / LOW grounding. We say “not enough evidence” when we can't prove it." },
                            { icon: Graph, title: "Analytics & audit trail", desc: "Every upload, query, share, and deletion is logged. Admin dashboard shows latency, cost, feedback, and more." },
                        ].map((f, i) => (
                            <div key={i} className="border-r border-b border-border p-8 dc-card-hover bg-card" data-testid={`platform-feature-${i}`}>
                                <f.icon size={28} weight="duotone" className="text-brand-primary" />
                                <h3 className="font-heading text-xl font-bold mt-4">{f.title}</h3>
                                <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{f.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Security section */}
            <section id="security" className="border-b border-border py-20 bg-secondary/30">
                <div className="max-w-7xl mx-auto px-6 md:px-10 grid md:grid-cols-12 gap-8">
                    <div className="md:col-span-5">
                        <div className="dc-overline mb-4">Security</div>
                        <h2 className="font-heading font-black text-4xl tracking-tighter">
                            Zero document leakage.<br />By design.
                        </h2>
                    </div>
                    <div className="md:col-span-7 space-y-6">
                        {[
                            ["Server-side scoping", "Every retrieval query is restricted to the share token's document_ids list — enforced in the vector search WHERE clause, not the UI."],
                            ["Revoke instantly", "Kill any share link the moment you need to. Active guests get 401 on their next request."],
                            ["Full audit trail", "Who uploaded what, when a guest opened a link, every query they asked. All captured, all searchable."],
                            ["Secure deletion", "Delete removes the file, every chunk, every embedding, and every cached result. With a receipt in the audit log."],
                        ].map(([t, d], i) => (
                            <div key={i} className="border-l-2 border-brand-primary pl-5" data-testid={`security-point-${i}`}>
                                <div className="font-heading font-bold">{t}</div>
                                <div className="text-sm text-muted-foreground mt-1">{d}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section id="pricing" className="py-20">
                <div className="max-w-4xl mx-auto px-6 md:px-10 text-center">
                    <h2 className="font-heading font-black text-4xl md:text-5xl tracking-tighter">
                        Ready to ground your AI?
                    </h2>
                    <p className="text-muted-foreground mt-4 text-lg">
                        Create a workspace in 30 seconds. Upload your first document. Get grounded answers today.
                    </p>
                    <Link to="/register">
                        <Button size="lg" className="h-12 px-8 mt-8" data-testid="footer-cta-button">
                            Start free <ArrowRight size={18} className="ml-1" />
                        </Button>
                    </Link>
                </div>
            </section>

            <footer className="border-t border-border py-10">
                <div className="max-w-7xl mx-auto px-6 md:px-10 flex flex-wrap items-center justify-between gap-4 text-xs text-muted-foreground">
                    <div>© 2026 DocChat · Enterprise RAG Platform</div>
                    <div className="font-mono">v2.0.0</div>
                </div>
            </footer>
        </div>
    );
}
