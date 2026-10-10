// Centralized runtime configuration (Phase 1).
// All API URL references must go through here — no raw import.meta.env
// lookups elsewhere in src/.

export const API_URL =
  import.meta.env.VITE_API_URL ?? 'http://localhost:5000'

export const googleLoginUrl = `${API_URL}/auth/login`
