import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
    const token = localStorage.getItem("dc_access_token");
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

api.interceptors.response.use(
    (r) => r,
    async (err) => {
        const original = err.config;
        if (err?.response?.status === 401 && !original._retry) {
            original._retry = true;
            const refresh = localStorage.getItem("dc_refresh_token");
            if (refresh) {
                try {
                    const r = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refresh });
                    localStorage.setItem("dc_access_token", r.data.access_token);
                    localStorage.setItem("dc_refresh_token", r.data.refresh_token);
                    original.headers.Authorization = `Bearer ${r.data.access_token}`;
                    return api(original);
                } catch (e) {
                    localStorage.removeItem("dc_access_token");
                    localStorage.removeItem("dc_refresh_token");
                    localStorage.removeItem("dc_user");
                    window.location.href = "/login";
                }
            }
        }
        return Promise.reject(err);
    }
);

export default api;
