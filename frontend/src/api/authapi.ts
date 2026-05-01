import axios from 'axios'

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL
})

export const loginUser = (data: any) => API.post('/auth/login', data)

export const registerUser = (data: any) => API.post('/auth/register', data)

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
}