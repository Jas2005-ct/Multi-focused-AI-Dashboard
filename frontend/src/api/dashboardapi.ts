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
export const optimizeQuery = (sentence: string, dbId?: number) =>
  API.post('/api/sql-query/', { sentence, db_id: dbId })

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

export const selectConnection = (dbId: number) =>
  API.post('/api/select-connection/', { db_id: dbId })

export const testConnection = (dbId: number) =>
  API.post('/api/test-connection/', { db_id: dbId })

export const deleteConnection = (dbId: number) =>
  API.delete('/api/delete-connection/', { data: { db_id: dbId } })

export const getConnections = () =>
  API.get('/api/get-connections/')

// Get API health check
export const healthCheck = () =>
  API.get('/api/')

export default API
