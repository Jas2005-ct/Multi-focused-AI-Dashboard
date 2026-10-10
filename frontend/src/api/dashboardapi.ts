import axios from 'axios'
import API from './client'
import { API_URL } from '../config'

// Bare client for unauthenticated probes: no Bearer token, no 401
// interceptor — a status badge must never log the user out.
const publicClient = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

publicClient.interceptors.request.use((config) => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    config.headers['X-Request-ID'] = crypto.randomUUID()
  }
  return config
})

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
  API.post('/api/db-connection', connectionData)

export const selectConnection = (dbId: number) =>
  API.get('/api/get-connections/', { params: { db_id: dbId } })

export const testConnection = (dbId: number) =>
  API.post('/api/test-connection/', { db_id: dbId })

export const deleteConnection = (dbId: number) =>
  API.delete('/api/delete-connection', { data: { db_id: dbId } })

export const getConnections = () =>
  API.get('/api/get-connections/')

// Get API health check
export const healthCheck = () =>
  API.get('/api/')

// Unauthenticated liveness probe for the status badge (Phase 1)
export const apiStatus = () =>
  publicClient.get('/health')

export default API
