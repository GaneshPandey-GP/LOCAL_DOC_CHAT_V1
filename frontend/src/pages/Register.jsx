import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

export default function Register() {
    const { register } = useAuth();
    const nav = useNavigate();
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            await register(name, email, password);
            toast.success("Workspace created");
            nav("/app");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Registration failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="min-h-screen grid md:grid-cols-2">
            <div className="hidden md:flex border-r border-border bg-secondary/30 p-12 flex-col justify-between">
                <Link to="/" className="flex items-center gap-2" data-testid="register-brand-link">
                    <div className="w-7 h-7 bg-brand-primary grid place-items-center">
                        <span className="text-white font-heading font-black text-sm">D</span>
                    </div>
                    <span className="font-heading font-bold text-lg">DocChat</span>
                </Link>
                <div>
                    <div className="dc-overline mb-3">30 seconds</div>
                    <h1 className="font-heading font-black text-4xl tracking-tighter leading-tight">
                        Create your<br />workspace.
                    </h1>
                    <p className="text-sm text-muted-foreground mt-4 max-w-sm">
                        Your first account becomes the Owner. Invite your team from the admin panel.
                    </p>
                </div>
                <div className="text-xs text-muted-foreground font-mono">No credit card · Self-hosted ready</div>
            </div>

            <div className="flex items-center justify-center p-8 md:p-12">
                <form onSubmit={submit} className="w-full max-w-sm space-y-6" data-testid="register-form">
                    <div>
                        <div className="dc-overline mb-2">Register</div>
                        <h2 className="font-heading text-3xl font-black tracking-tight">Start your workspace</h2>
                    </div>

                    <div className="space-y-4">
                        <div>
                            <Label htmlFor="name" className="dc-overline">Name</Label>
                            <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} className="mt-1 h-11" data-testid="register-name-input" />
                        </div>
                        <div>
                            <Label htmlFor="email" className="dc-overline">Email</Label>
                            <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 h-11" data-testid="register-email-input" />
                        </div>
                        <div>
                            <Label htmlFor="password" className="dc-overline">Password</Label>
                            <Input id="password" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 h-11" data-testid="register-password-input" />
                            <p className="text-xs text-muted-foreground mt-1">6+ characters</p>
                        </div>
                    </div>

                    <Button type="submit" className="w-full h-11" disabled={busy} data-testid="register-submit-button">
                        {busy ? "Creating…" : "Create workspace"}
                    </Button>

                    <div className="text-sm text-muted-foreground text-center">
                        Already have an account?{" "}
                        <Link to="/login" className="text-brand-primary font-medium underline underline-offset-2" data-testid="register-login-link">
                            Sign in
                        </Link>
                    </div>
                </form>
            </div>
        </div>
    );
}
