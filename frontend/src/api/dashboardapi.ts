import axios from 'axios'
import { getToken } from './authapi'

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  withCredentials: true
})

// Add authorization header to requests
API.interceptors.request.use(((config: any) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
}) as any)

// SQL Query Optimization
export const optimizeQuery = (sentence: string) =>
  API.post('/api/sql-query/', { sentence })

// Database Connection Management
export const saveDBConnection = (connectionData: {
  host: string
  port: number
  database: string
  username: string
  password: string
  connection_string?: string
}) =>
  API.post('/api/db-connection/', connectionData)

// Get API health check
export const healthCheck = () =>
  API.get('/api/')

export default API
