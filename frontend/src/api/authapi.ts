import axios from 'axios'
import type { LoginRequest, RegisterRequest, AuthSuccess } from '../types/auth'

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL
})

export const loginUser = (data: LoginRequest) => API.post<AuthSuccess>('/auth/login', data)

export const registerUser = (data: RegisterRequest) => API.post<AuthSuccess>('/auth/register', data)

export const googleLoginUser = (token: string) =>
  API.post('/auth/login', { token })

export default API



export const saveToken = (token: string) => {
   localStorage.setItem("token", token)
}

export const getToken = () => {
   return localStorage.getItem("token")
}

export const logoutUser = () => {
   localStorage.removeItem("token")
   localStorage.removeItem("user")
}

export const saveUser = (user: { name: string; email: string; id: number }) => {
   localStorage.setItem("user", JSON.stringify(user))
}

export const getUser = () => {
   const userStr = localStorage.getItem("user")
   if (!userStr) return null
   try {
      return JSON.parse(userStr) as { name: string; email: string; id: number }
   } catch {
      return null
   }
}