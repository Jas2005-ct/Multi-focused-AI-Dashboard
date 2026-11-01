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

// --- AI query (versioned surface) ---

export type AiQueryMode = 'auto' | 'sql' | 'answer'

export interface AiQueryRequest {
  query: string
  connection_id: number
  mode?: AiQueryMode
}

/** AI query via the versioned endpoint (LangGraph agent or LCEL chain). */
export const aiQuery = (payload: AiQueryRequest) =>
  API.post('/api/v1/ai/query', payload)

// --- Database connection management (versioned surface) ---

export const getConnections = (page = 1, perPage = 20) =>
  API.get('/api/v1/connections', { params: { page, per_page: perPage } })

export const getConnection = (dbId: number) =>
  API.get(`/api/v1/connections/${dbId}`)

export const saveDBConnection = (connectionData: {
  name?: string
  host: string
  port: number
  database: string
  username: string
  password: string
  db_type?: string
  connection_string?: string
  sslmode?: string
}) =>
  API.post('/api/v1/connections', connectionData)

export const testConnection = (dbId: number) =>
  API.post(`/api/v1/connections/${dbId}/test`)

export const deleteConnection = (dbId: number) =>
  API.delete(`/api/v1/connections/${dbId}`)

// Unauthenticated liveness probe for the status badge (Phase 1)
export const apiStatus = () =>
  publicClient.get('/health')

export default API
