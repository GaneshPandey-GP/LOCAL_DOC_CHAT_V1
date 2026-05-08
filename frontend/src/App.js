import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/lib/auth";

import Login from "@/pages/Login";
import AppLayout from "@/pages/AppLayout";
import Dashboard from "@/pages/Dashboard";
import Chat from "@/pages/Chat";
import ShareLinks from "@/pages/ShareLinks";
import GuestShare from "@/pages/GuestShare";
import AdminAnalytics from "@/pages/AdminAnalytics";
import AdminAudit from "@/pages/AdminAudit";
import AdminUsers from "@/pages/AdminUsers";
import Settings from "@/pages/Settings";
import EmbedWidget from "@/pages/EmbedWidget";
import AdminFlags from "@/pages/AdminFlags";
import ShareHistory from "@/pages/ShareHistory";

import "@/App.css";

function PrivateRoute({ children, requireRole }) {
    const { user, loading } = useAuth();
    if (loading) return <div className="p-10 text-sm text-muted-foreground">Loading…</div>;
    if (!user) return <Navigate to="/login" replace />;
    if (requireRole && user.role !== requireRole && user.role !== "owner") return <Navigate to="/app" replace />;
    return children;
}

function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<Navigate to="/login" replace />} />
                    <Route path="/login" element={<Login />} />
                    <Route path="/share/:token" element={<GuestShare />} />
                    <Route path="/app" element={<PrivateRoute><AppLayout /></PrivateRoute>}>
                        <Route index element={<Dashboard />} />
                        <Route path="chat" element={<Chat />} />
                        <Route path="chat/:sessionId" element={<Chat />} />
                        <Route path="shares" element={<ShareLinks />} />
                        <Route path="shares/history" element={<ShareHistory />} />
                        <Route path="embed-widget" element={<EmbedWidget />} />
                        <Route path="settings" element={<Settings />} />
                        <Route path="admin/analytics" element={<PrivateRoute requireRole="owner"><AdminAnalytics /></PrivateRoute>} />
                        <Route path="admin/audit" element={<PrivateRoute requireRole="owner"><AdminAudit /></PrivateRoute>} />
                        <Route path="admin/users" element={<PrivateRoute requireRole="owner"><AdminUsers /></PrivateRoute>} />
                        <Route path="admin/flags" element={<PrivateRoute requireRole="owner"><AdminFlags /></PrivateRoute>} />
                    </Route>
                    <Route path="*" element={<Navigate to="/login" replace />} />
                </Routes>
            </BrowserRouter>
            <Toaster position="top-right" />
        </AuthProvider>
    );
}

export default App;
