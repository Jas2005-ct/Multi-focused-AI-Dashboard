import axios from "axios";
import { API_URL } from "../config";

const PUBLIC_PATHS = ["/", "/register", "/forgot-password"];

const client = axios.create({
  baseURL: API_URL,
  withCredentials: true,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    config.headers["X-Request-ID"] = crypto.randomUUID();
  }
  return config;
});

// Global expired/invalid-token handling: clear credentials and bounce to
// login unless already on a public route (avoids redirect loops).
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error?.response?.status === 401 &&
      !PUBLIC_PATHS.includes(window.location.pathname)
    ) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/";
    }
    return Promise.reject(error);
  }
);

export default client;
