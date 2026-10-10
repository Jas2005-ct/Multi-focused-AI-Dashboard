import axios, { type AxiosRequestConfig } from "axios";
import { API_URL } from "../config";

const PUBLIC_PATHS = ["/", "/register", "/forgot-password"];

const TOKEN_KEY = "token";
const REFRESH_KEY = "refreshToken";
const USER_KEY = "user";

const client = axios.create({
  baseURL: API_URL,
  withCredentials: true,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    config.headers["X-Request-ID"] = crypto.randomUUID();
  }
  return config;
});

// Single-flight refresh: concurrent TOKEN_EXPIRED responses share one
// rotation. Required — reuse detection burns the family on double use.
let refreshPromise: Promise<string> | null = null;

function rotateSession(): Promise<string> {
  if (!refreshPromise) {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return Promise.reject(new Error("no refresh token"));
    refreshPromise = axios
      .post(`${API_URL}/auth/refresh`, { refreshToken })
      .then((res) => {
        localStorage.setItem(TOKEN_KEY, res.data.token);
        localStorage.setItem(REFRESH_KEY, res.data.refreshToken);
        if (res.data.user) {
          localStorage.setItem(USER_KEY, JSON.stringify(res.data.user));
        }
        return res.data.token as string;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function logoutAndRedirect() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
  if (!PUBLIC_PATHS.includes(window.location.pathname)) {
    window.location.href = "/";
  }
}

// Global expired/invalid-token handling: rotate once on TOKEN_EXPIRED,
// otherwise clear credentials and bounce to login (no redirect loops).
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = (error?.config ?? {}) as AxiosRequestConfig & {
      _retry?: boolean;
    };
    if (
      error?.response?.status === 401 &&
      error?.response?.data?.code === "TOKEN_EXPIRED" &&
      !original._retry
    ) {
      original._retry = true;
      try {
        const token = await rotateSession();
        original.headers = {
          ...(original.headers as Record<string, string>),
          Authorization: `Bearer ${token}`,
        };
        return client(original);
      } catch {
        // rotation failed — fall through to logout
      }
    }
    if (error?.response?.status === 401) {
      logoutAndRedirect();
    }
    return Promise.reject(error);
  },
);

export default client;
