import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

export default function Login() {
    const { login } = useAuth();
    const nav = useNavigate();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            await login(email, password);
            toast.success("Welcome back");
            nav("/app");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Login failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="min-h-screen grid md:grid-cols-2">
            <div className="hidden md:flex border-r border-border bg-secondary/30 p-12 flex-col justify-between">
                <Link to="/" className="flex items-center gap-2" data-testid="login-brand-link">
                    <div className="w-7 h-7 bg-brand-primary grid place-items-center">
                        <span className="text-white font-heading font-black text-sm">D</span>
                    </div>
                    <span className="font-heading font-bold text-lg">DocChat</span>
                </Link>
                <div>
                    <div className="dc-overline mb-3">Enterprise RAG</div>
                    <h1 className="font-heading font-black text-4xl tracking-tighter leading-tight">
                        Welcome back<br />to your workspace.
                    </h1>
                    <p className="text-sm text-muted-foreground mt-4 max-w-sm">
                        Pick up where you left off. Your sessions, documents, and share links are ready.
                    </p>
                </div>
                <div className="text-xs text-muted-foreground font-mono">SOC 2 · RBAC · Audit-logged</div>
            </div>

            <div className="flex items-center justify-center p-8 md:p-12">
                <form onSubmit={submit} className="w-full max-w-sm space-y-6" data-testid="login-form">
                    <div>
                        <div className="dc-overline mb-2">Sign in</div>
                        <h2 className="font-heading text-3xl font-black tracking-tight">Access your workspace</h2>
                    </div>

                    <div className="space-y-4">
                        <div>
                            <Label htmlFor="email" className="dc-overline">Email</Label>
                            <Input
                                id="email"
                                type="email"
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="mt-1 h-11"
                                data-testid="login-email-input"
                            />
                        </div>
                        <div>
                            <Label htmlFor="password" className="dc-overline">Password</Label>
                            <Input
                                id="password"
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="mt-1 h-11"
                                data-testid="login-password-input"
                            />
                        </div>
                    </div>

                    <Button type="submit" className="w-full h-11" disabled={busy} data-testid="login-submit-button">
                        {busy ? "Signing in…" : "Sign in"}
                    </Button>
                </form>
            </div>
        </div>
    );
}
