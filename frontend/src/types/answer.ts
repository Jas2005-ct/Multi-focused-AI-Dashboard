/** A single row returned by the agent's read-only tools. */
export type AnswerRow = Record<string, unknown>

/** Payload carried in the `data` field of the v1 AI query envelope. */
export interface AiQueryData {
  type: 'query' | 'answer'
  sql?: string
  answer?: string
  tables?: string[]
  /** The table the rows came from, when the agent used exactly one. */
  table?: string | null
  rows?: AnswerRow[]
  count?: number | null
  toolCalls?: { name: string; args: Record<string, unknown> }[]
}
