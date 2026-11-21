// Centralized runtime configuration (Phase 1).
// All API URL references must go through here — no raw import.meta.env
// lookups elsewhere in src/.

export const API_URL =
  import.meta.env.VITE_API_URL ?? 'http://localhost:5000'

export const googleLoginUrl = `${API_URL}/auth/login`

/**
 * TEMPORARY DEMO MODE: authentication is disabled so visitors can explore
 * the demo database without signing in. The dashboard skips the login screen
 * and the backend treats every request as the shared demo user.
 * TODO: set this back to true (and the backend AUTH_REQUIRED=true) to
 * re-enable login/authentication.
 */
export const AUTH_REQUIRED = false

/**
 * Google sign-in is disabled by default.
 *
 * Set VITE_ENABLE_GOOGLE_OAUTH=true (and configure the backend with
 * ENABLE_GOOGLE_OAUTH=true plus the Google client id/secret) to bring the
 * "Continue with Google" button back on the login and register pages.
 */
export const enableGoogleOAuth =
  import.meta.env.VITE_ENABLE_GOOGLE_OAUTH === 'true'
