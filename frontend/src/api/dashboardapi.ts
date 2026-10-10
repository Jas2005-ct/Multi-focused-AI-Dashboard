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

// Database Connection Management (Phase 3: /api/v1/connections)
export const getConnections = (page = 1, perPage = 20) =>
  API.get('/api/v1/connections', { params: { page, per_page: perPage } })

export const getConnection = (dbId: number) =>
  API.get(`/api/v1/connections/${dbId}`)

export const saveDBConnection = (connectionData: {
  host: string
  port: number
  database: string
  username: string
  password: string
  db_type?: string
  connection_string?: string
  name?: string
  sslmode?: string
}) =>
  API.post('/api/v1/connections', connectionData)

export const testConnection = (dbId: number) =>
  API.post(`/api/v1/connections/${dbId}/test`)

export const deleteConnection = (dbId: number) =>
  API.delete(`/api/v1/connections/${dbId}`)

export const getTables = (dbId: number) =>
  API.get(`/api/v1/connections/${dbId}/tables`)

export const getTableSchema = (dbId: number, tableName: string) =>
  API.get(`/api/v1/connections/${dbId}/tables/${tableName}`)

// Get API health check
export const healthCheck = () =>
  API.get('/api/')

// Unauthenticated liveness probe for the status badge (Phase 1)
export const apiStatus = () =>
  publicClient.get('/health')

export default API