export interface AuthError {
  error: string
  message?: string
}

export interface AuthUser {
  id: number
  email: string
  name: string
}

export interface AuthSuccess {
  token: string
  user: AuthUser
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
}
