import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function AdminUsers() {
    const { user: currentUser } = useAuth();
    const [users, setUsers] = useState([]);
    const [createOpen, setCreateOpen] = useState(false);
    const [form, setForm] = useState({ name: "", email: "", password: "", role: "editor" });
    const [busy, setBusy] = useState(false);

    const load = () => api.get("/admin/users").then((r) => setUsers(r.data)).catch(() => {});
    useEffect(() => { load(); }, []);

    const changeRole = async (userId, role) => {
        try {
            await api.patch(`/admin/users/${userId}`, { role });
            toast.success("Role updated");
            setUsers((c) => c.map((u) => (u.id === userId ? { ...u, role } : u)));
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Update failed");
        }
    };

    const submitCreate = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const r = await api.post("/admin/users", form);
            toast.success(`${r.data.role === "owner" ? "Owner" : "Editor"} created`);
            setUsers((c) => [r.data, ...c]);
            setCreateOpen(false);
            setForm({ name: "", email: "", password: "", role: "editor" });
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Create failed");
        } finally {
            setBusy(false);
        }
    };

    const removeUser = async (u) => {
        if (!window.confirm(`Delete ${u.email}? They'll lose access immediately.`)) return;
        try {
            await api.delete(`/admin/users/${u.id}`);
            toast.success("User deleted");
            setUsers((c) => c.filter((x) => x.id !== u.id));
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Delete failed");
        }
    };

    return (
        <div>
            <header className="h-16 border-b border-border px-8 flex items-center justify-between sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Admin</div>
                    <h1 className="font-heading font-bold text-lg">Users</h1>
                </div>
                <Button onClick={() => setCreateOpen(true)} data-testid="create-user-button">
                    <Plus size={16} /> New editor
                </Button>
            </header>
            <div className="p-8 max-w-5xl">
                <div className="border border-border">
                    <div className="grid grid-cols-[1fr_1fr_140px_160px_44px] gap-4 px-4 py-3 bg-secondary/50 border-b border-border text-xs font-mono uppercase tracking-wider text-muted-foreground">
                        <div>Name</div>
                        <div>Email</div>
                        <div>Joined</div>
                        <div>Role</div>
                        <div></div>
                    </div>
                    {users.map((u) => (
                        <div key={u.id} className="grid grid-cols-[1fr_1fr_140px_160px_44px] gap-4 px-4 py-3 border-b border-border last:border-b-0 items-center" data-testid={`user-row-${u.id}`}>
                            <div className="font-medium">{u.name}</div>
                            <div className="text-sm font-mono text-muted-foreground truncate">{u.email}</div>
                            <div className="text-xs font-mono text-muted-foreground">{new Date(u.created_at).toLocaleDateString()}</div>
                            <Select value={u.role} onValueChange={(v) => changeRole(u.id, v)}>
                                <SelectTrigger className="h-8 text-xs" data-testid={`role-select-${u.id}`}>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="owner">Owner</SelectItem>
                                    <SelectItem value="editor">Editor</SelectItem>
                                </SelectContent>
                            </Select>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => removeUser(u)}
                                disabled={u.id === currentUser?.id}
                                title={u.id === currentUser?.id ? "Cannot delete yourself" : "Delete user"}
                                data-testid={`delete-user-${u.id}`}
                            >
                                <Trash size={16} />
                            </Button>
                        </div>
                    ))}
                </div>
            </div>

            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                <DialogContent data-testid="create-user-dialog">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">New user</DialogTitle>
                        <DialogDescription>
                            Create an editor or owner account. They'll log in with the email + password you set.
                        </DialogDescription>
                    </DialogHeader>
                    <form onSubmit={submitCreate} className="space-y-4">
                        <div>
                            <Label htmlFor="cu-name" className="dc-overline">Name</Label>
                            <Input id="cu-name" required value={form.name}
                                onChange={(e) => setForm({ ...form, name: e.target.value })}
                                className="mt-1" data-testid="create-user-name" />
                        </div>
                        <div>
                            <Label htmlFor="cu-email" className="dc-overline">Email</Label>
                            <Input id="cu-email" type="email" required value={form.email}
                                onChange={(e) => setForm({ ...form, email: e.target.value })}
                                className="mt-1" data-testid="create-user-email" />
                        </div>
                        <div>
                            <Label htmlFor="cu-pass" className="dc-overline">Password</Label>
                            <Input id="cu-pass" type="password" required minLength={6} value={form.password}
                                onChange={(e) => setForm({ ...form, password: e.target.value })}
                                className="mt-1" data-testid="create-user-password" />
                        </div>
                        <div>
                            <Label className="dc-overline">Role</Label>
                            <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                                <SelectTrigger className="mt-1" data-testid="create-user-role">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="editor">Editor</SelectItem>
                                    <SelectItem value="owner">Owner</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <DialogFooter>
                            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                                Cancel
                            </Button>
                            <Button type="submit" disabled={busy} data-testid="create-user-submit">
                                {busy ? "Creating…" : "Create"}
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>
        </div>
    );
}
