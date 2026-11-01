import axios from 'axios'

/** Standard success envelope returned by the versioned `/api/v1` surface. */
export interface ApiEnvelope<T> {
  success: boolean
  message: string
  data?: T
  request_id?: string
}

/** Error envelope returned by every backend error handler. */
export interface ApiErrorBody {
  success?: boolean
  error?: string
  message?: string
  details?: unknown
  request_id?: string
}

/** Page metadata returned inside a paginated `data` payload. */
export interface Paginated<T> {
  page: number
  per_page: number
  total: number
  pages: number
  connections: T[]
}

/** One entry of a flask-openapi3 / pydantic validation error list. */
export interface ValidationIssue {
  type?: string
  loc?: (string | number)[]
  msg?: string
  /** Pydantic echoes the rejected value here - never surface it. */
  input?: unknown
  ctx?: { error?: string }
}

/**
 * Extract a human-readable message from a rejected request.
 *
 * The backend always answers errors with the standard envelope, so the
 * message is usually available on `response.data.message` (and sometimes on
 * `response.data.error`). This keeps components free of `any` casts.
 */
export function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError<ApiErrorBody>(err)) {
    const body = err.response?.data
    if (body?.message) return body.message
    if (body?.error) return body.error
    const validation = getValidationMessage(err)
    if (validation) return validation
    if (err.message) return err.message
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}

/**
 * Read a pydantic validation error list (HTTP 422).
 *
 * flask-openapi3 answers a schema violation with a *list* of issues, not the
 * standard error envelope, so the generic error handler finds nothing and
 * falls back to a useless "Something went wrong" string.
 *
 * The offending input is deliberately dropped: for a password field it would
 * echo the plaintext back to the client.
 */
export function getValidationMessage(err: unknown): string | undefined {
  if (!axios.isAxiosError(err)) return undefined
  const body = err.response?.data
  if (!Array.isArray(body)) return undefined

  const issues = body as ValidationIssue[]
  const messages = issues
    .map((issue) => issue.ctx?.error ?? issue.msg)
    .filter((msg): msg is string => Boolean(msg))
    // Pydantic prefixes custom validators with "Value error, ".
    .map((msg) => msg.replace(/^Value error,\s*/i, ''))

  if (messages.length === 0) return undefined
  if (messages.length === 1) return messages[0]
  return messages.join('; ')
}

/** Same as {@link getErrorMessage} but also exposes the request id for logs. */
export function getErrorDetails(err: unknown): { message: string; requestId?: string } {
  if (axios.isAxiosError<ApiErrorBody>(err)) {
    const body = err.response?.data
    return {
      message: body?.message || body?.error || err.message || 'Request failed',
      requestId: body?.request_id,
    }
  }
  return { message: err instanceof Error ? err.message : 'Request failed' }
}
