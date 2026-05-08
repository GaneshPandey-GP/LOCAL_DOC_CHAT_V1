import React from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
    FileText,
    ChatCircleDots,
    LinkSimple,
    ChartLine,
    ListMagnifyingGlass,
    UsersThree,
    Gear,
    SignOut,
    CaretRight,
    Code,
    ToggleRight,
    ClockCounterClockwise,
} from "@phosphor-icons/react";

function NavItem({ to, end, icon: Icon, label, testId }) {
    return (
        <NavLink
            to={to}
            end={end}
            data-testid={testId}
            className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm border-l-2 transition-colors ${
                    isActive
                        ? "border-brand-primary bg-secondary font-medium text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                }`
            }
        >
            <Icon size={18} weight="duotone" />
            <span>{label}</span>
        </NavLink>
    );
}

export default function AppLayout() {
    const { user, logout } = useAuth();
    const nav = useNavigate();
    const isAdmin = user?.role === "owner";

    return (
        <div className="min-h-screen grid grid-cols-[260px_1fr]">
            <aside className="border-r border-border bg-background flex flex-col">
                <div className="h-16 border-b border-border flex items-center px-5">
                    <Link to="/app" className="flex items-center gap-2" data-testid="sidebar-brand">
                        <div className="w-7 h-7 bg-brand-primary grid place-items-center">
                            <span className="text-white font-heading font-black text-sm">D</span>
                        </div>
                        <span className="font-heading font-bold text-lg">DocChat</span>
                    </Link>
                </div>

                <nav className="flex-1 py-4 overflow-y-auto">
                    <div className="dc-overline px-5 mb-2">Workspace</div>
                    <NavItem to="/app" end icon={FileText} label="Documents" testId="nav-documents" />
                    <NavItem to="/app/chat" icon={ChatCircleDots} label="Chat" testId="nav-chat" />
                    <NavItem to="/app/shares" icon={LinkSimple} label="Share links" testId="nav-shares" />
                    <NavItem to="/app/shares/history" icon={ClockCounterClockwise} label="Share Link History" testId="nav-share-history" />
                    <NavItem to="/app/embed-widget" icon={Code} label="Embed widget" testId="nav-embed-widget" />

                    {isAdmin && (
                        <>
                            <div className="dc-overline px-5 mb-2 mt-6">Admin</div>
                            <NavItem to="/app/admin/analytics" icon={ChartLine} label="Analytics" testId="nav-admin-analytics" />
                            <NavItem to="/app/admin/audit" icon={ListMagnifyingGlass} label="Audit log" testId="nav-admin-audit" />
                            <NavItem to="/app/admin/users" icon={UsersThree} label="Users" testId="nav-admin-users" />
                            <NavItem to="/app/admin/flags" icon={ToggleRight} label="Feature flags" testId="nav-admin-flags" />
                        </>
                    )}

                    <div className="dc-overline px-5 mb-2 mt-6">Account</div>
                    <NavItem to="/app/settings" icon={Gear} label="Settings" testId="nav-settings" />
                </nav>

                <div className="border-t border-border p-4">
                    <div className="flex items-center gap-3">
                        <div className="w-9 h-9 bg-brand-primary grid place-items-center text-white font-heading font-bold text-sm">
                            {(user?.name || "?").charAt(0).toUpperCase()}
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium truncate" data-testid="sidebar-user-name">{user?.name}</div>
                            <div className="text-[11px] text-muted-foreground font-mono uppercase" data-testid="sidebar-user-role">{user?.role}</div>
                        </div>
                        <Button
                            size="icon"
                            variant="ghost"
                            onClick={() => { logout(); nav("/login"); }}
                            data-testid="logout-button"
                            title="Log out"
                        >
                            <SignOut size={16} />
                        </Button>
                    </div>
                </div>
            </aside>

            <main className="overflow-auto">
                <Outlet />
            </main>
        </div>
    );
}
