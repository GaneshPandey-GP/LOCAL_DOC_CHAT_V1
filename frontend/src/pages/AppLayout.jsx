import React, { useState } from "react";
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
    Code,
    ToggleRight,
    ClockCounterClockwise,
    List as Hamburger,
    X,
    Database,
    BookOpen,
    Wrench,
    ChartBar,
} from "@phosphor-icons/react";

function NavItem({ to, end, icon: Icon, label, testId, onNavigate }) {
    return (
        <NavLink
            to={to}
            end={end}
            data-testid={testId}
            onClick={onNavigate}
            className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm border-l-2 transition-colors min-h-[44px] ${
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
    const isAdmin = user?.role === "admin";

    // Stream 7 — mobile sidebar drawer state
    const [mobileOpen, setMobileOpen] = useState(false);
    const closeMobile = () => setMobileOpen(false);

    const sidebar = (
        <>
            {/* Brand header — flex-shrink-0 so it never gets squished */}
            <div className="h-16 border-b border-border flex items-center justify-between px-5 flex-shrink-0">
                <Link to="/app" className="flex items-center gap-2" data-testid="sidebar-brand" onClick={closeMobile}>
                    <div className="w-7 h-7 bg-brand-primary grid place-items-center">
                        <span className="text-white font-heading font-black text-sm">D</span>
                    </div>
                    <span className="font-heading font-bold text-lg">DocChat</span>
                </Link>
                <button
                    className="md:hidden w-9 h-9 flex items-center justify-center text-muted-foreground hover:text-foreground"
                    onClick={closeMobile}
                    aria-label="Close menu"
                    data-testid="sidebar-close"
                >
                    <X size={18} />
                </button>
            </div>

            <nav className="flex-1 py-4 overflow-y-auto min-h-0">
                <div className="dc-overline px-5 mb-2">Workspace</div>
                <NavItem to="/app" end icon={FileText} label="Documents" testId="nav-documents" onNavigate={closeMobile} />
                <NavItem to="/app/chat" icon={ChatCircleDots} label="Chat" testId="nav-chat" onNavigate={closeMobile} />
                <NavItem to="/app/db-agent" icon={Database} label="DB Agent" testId="nav-db-agent" onNavigate={closeMobile} />
                <NavItem to="/app/shares" icon={LinkSimple} label="Share links" testId="nav-shares" onNavigate={closeMobile} />
                <NavItem to="/app/shares/history" icon={ClockCounterClockwise} label="Share Link History" testId="nav-share-history" onNavigate={closeMobile} />
                <NavItem to="/app/embed-widget" icon={Code} label="Embed widget" testId="nav-embed-widget" onNavigate={closeMobile} />

                <div className="dc-overline px-5 mb-2 mt-6">Knowledge</div>
                <NavItem to="/app/kb" icon={BookOpen} label="Knowledge Bases" testId="nav-kb" onNavigate={closeMobile} />

                <div className="dc-overline px-5 mb-2 mt-6">AI Studio</div>
                <NavItem to="/app/mcp" icon={Wrench} label="MCP Tools" testId="nav-mcp" onNavigate={closeMobile} />

                {isAdmin && (
                    <>
                        <div className="dc-overline px-5 mb-2 mt-6">Admin</div>
                        <NavItem to="/app/admin/analytics" icon={ChartLine} label="Analytics" testId="nav-admin-analytics" onNavigate={closeMobile} />
                        <NavItem to="/app/admin/audit" icon={ListMagnifyingGlass} label="Audit log" testId="nav-admin-audit" onNavigate={closeMobile} />
                        <NavItem to="/app/admin/users" icon={UsersThree} label="Users" testId="nav-admin-users" onNavigate={closeMobile} />
                        <NavItem to="/app/admin/flags" icon={ToggleRight} label="Feature flags" testId="nav-admin-flags" onNavigate={closeMobile} />
                        <NavItem to="/app/admin/model-analytics" icon={ChartBar} label="Model Analytics" testId="nav-model-analytics" onNavigate={closeMobile} />
                    </>
                )}

                <div className="dc-overline px-5 mb-2 mt-6">Account</div>
                <NavItem to="/app/settings" icon={Gear} label="Settings" testId="nav-settings" onNavigate={closeMobile} />
            </nav>

            <div className="border-t border-border p-4 flex-shrink-0">
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
                        className="min-h-[44px] min-w-[44px]"
                    >
                        <SignOut size={16} />
                    </Button>
                </div>
            </div>
        </>
    );

    return (
        <div className="h-screen overflow-hidden md:grid md:grid-cols-[260px_1fr] flex flex-col">
            {/* Stream 7 — Mobile top bar with hamburger */}
            <div className="md:hidden h-14 border-b border-border bg-background flex items-center justify-between px-3 flex-shrink-0">
                <button
                    className="w-10 h-10 flex items-center justify-center text-foreground"
                    onClick={() => setMobileOpen(true)}
                    aria-label="Open menu"
                    data-testid="sidebar-open"
                >
                    <Hamburger size={22} />
                </button>
                <Link to="/app" className="flex items-center gap-2">
                    <div className="w-6 h-6 bg-brand-primary grid place-items-center">
                        <span className="text-white font-heading font-black text-xs">D</span>
                    </div>
                    <span className="font-heading font-bold">DocChat</span>
                </Link>
                <div className="w-10" />
            </div>

            {/* Desktop sidebar */}
            <aside className="hidden md:flex border-r border-border bg-background flex-col overflow-hidden">
                {sidebar}
            </aside>

            {/* Mobile drawer */}
            {mobileOpen && (
                <div className="md:hidden fixed inset-0 z-50 flex" data-testid="sidebar-drawer">
                    <div
                        className="absolute inset-0 bg-black/40"
                        onClick={closeMobile}
                        aria-hidden
                    />
                    <aside className="relative bg-background border-r border-border w-72 max-w-[85vw] flex flex-col overflow-hidden">
                        {sidebar}
                    </aside>
                </div>
            )}

            <main className="overflow-auto min-h-0 flex-1">
                <Outlet />
            </main>
        </div>
    );
}
