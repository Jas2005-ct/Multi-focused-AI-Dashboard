import type { LoginRequest, RegisterRequest, AuthSuccess, AuthUser } from '../types/auth'
import API from './client'

const TOKEN_KEY = 'token'
const REFRESH_KEY = 'refreshToken'
const USER_KEY = 'user'

export const loginUser = (data: LoginRequest) => API.post<AuthSuccess>('/auth/login', data)

export const registerUser = (data: RegisterRequest) =>
  API.post<AuthSuccess>('/auth/register', data)

export const refreshSession = (refreshToken: string) =>
  API.post<AuthSuccess>('/auth/refresh', { refreshToken })

export const forgotPassword = (email: string) =>
  API.post('/auth/forgot-password', { email })

export const resendOtp = (email: string) => API.post('/auth/resend-otp', { email })

export const verifyOtp = (email: string, otp: string) =>
  API.post('/auth/verify-otp', { email, otp })

export const resetPassword = (email: string, otp: string, new_password: string) =>
  API.post('/auth/reset-password', { email, otp, new_password })

export default API

export const saveToken = (token: string) => {
  localStorage.setItem(TOKEN_KEY, token)
}

export const getToken = () => {
  return localStorage.getItem(TOKEN_KEY)
}

export const saveRefreshToken = (refreshToken: string) => {
  localStorage.setItem(REFRESH_KEY, refreshToken)
}

export const getRefreshToken = () => {
  return localStorage.getItem(REFRESH_KEY)
}

/** Persist a full login/refresh pair (Phase 2 token rotation). */
export const saveAuth = (auth: AuthSuccess) => {
  saveToken(auth.token)
  saveRefreshToken(auth.refreshToken)
  saveUser(auth.user)
}

export const clearAuth = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

export const logoutUser = async () => {
  try {
    await API.post('/auth/logout')
  } catch {
    // ignore network errors on logout
  } finally {
    clearAuth()
  }
}

export const saveUser = (user: AuthUser) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export const getUser = () => {
  const userStr = localStorage.getItem(USER_KEY)
  if (!userStr) return null
  try {
    return JSON.parse(userStr) as AuthUser
  } catch {
    return null
  }
}
