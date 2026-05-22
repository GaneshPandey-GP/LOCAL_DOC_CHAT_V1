import React, { createContext, useContext, useEffect, useState } from "react";
import api from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(() => {
        try { return JSON.parse(localStorage.getItem("dc_user") || "null"); } catch { return null; }
    });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const t = localStorage.getItem("dc_access_token");
        if (!t) { setLoading(false); return; }
        api.get("/auth/me")
            .then((r) => {
                setUser(r.data.user);
                localStorage.setItem("dc_user", JSON.stringify(r.data.user));
            })
            .catch(() => {
                localStorage.removeItem("dc_access_token");
                localStorage.removeItem("dc_refresh_token");
                localStorage.removeItem("dc_user");
                setUser(null);
            })
            .finally(() => setLoading(false));
    }, []);

    const login = async (email, password) => {
        const r = await api.post("/auth/login", { email, password });
        localStorage.setItem("dc_access_token", r.data.access_token);
        localStorage.setItem("dc_refresh_token", r.data.refresh_token);
        localStorage.setItem("dc_user", JSON.stringify(r.data.user));
        setUser(r.data.user);
        return r.data.user;
    };

    const register = async (name, email, password) => {
        const r = await api.post("/auth/register", { name, email, password });
        localStorage.setItem("dc_access_token", r.data.access_token);
        localStorage.setItem("dc_refresh_token", r.data.refresh_token);
        localStorage.setItem("dc_user", JSON.stringify(r.data.user));
        setUser(r.data.user);
        return r.data.user;
    };

    const logout = () => {
        localStorage.removeItem("dc_access_token");
        localStorage.removeItem("dc_refresh_token");
        localStorage.removeItem("dc_user");
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
