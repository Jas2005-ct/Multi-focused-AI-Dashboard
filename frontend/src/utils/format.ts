/**
 * Cell formatting for the agent's result table.
 *
 * The rows come straight from the target database, so their values are
 * whatever the driver returned: strings, numbers, ISO timestamps, JSON
 * blobs, nulls. Rendering them with `String(value)` produced `undefined`
 * for missing keys and `[object Object]` for JSON columns.
 */

/** How a single cell should be rendered. */
export interface FormattedCell {
  /** What to show in the cell. */
  text: string
  /** Tooltip with the untruncated value; omitted when there is nothing extra. */
  title?: string
  /** True when the value is a number — the column is right-aligned. */
  numeric: boolean
  /** True when the value was null/undefined — rendered as a dim em dash. */
  empty: boolean
  /** Set when the value is an http(s) URL. */
  href?: string
  /** Set when the value is an object/array — rendered as a code block. */
  code?: string
}

const ISO_DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/
const URL_RE = /^https?:\/\/\S+$/i

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Format a date-only value as a local calendar date.
 *
 * `new Date('2026-04-05')` parses as UTC midnight, which renders as the
 * *previous* day in negative-offset timezones and gains a spurious time
 * everywhere else. Building the date from its parts keeps it on the day the
 * database meant.
 */
function formatDateOnly(text: string): string | null {
  const [year, month, day] = text.split('-').map(Number)
  if (!year || !month || !day) return null
  const local = new Date(year, month - 1, day)
  if (Number.isNaN(local.getTime())) return null
  return local.toLocaleDateString()
}

/**
 * Format one raw cell value.
 *
 * @param value the raw value from the driver
 * @param column the column name — used only to make the tooltip clearer
 */
export function formatCell(value: unknown, column?: string): FormattedCell {
  if (value === null || value === undefined) {
    return { text: '—', numeric: false, empty: true }
  }

  if (typeof value === 'number') {
    // Rendered exactly as the driver returned it. toLocaleString() would
    // regroup digits per the browser locale (1234567 -> "12,34,567" under
    // en-IN), which silently changes the value the database holds.
    return {
      text: String(value),
      numeric: true,
      empty: false,
    }
  }

  if (typeof value === 'boolean') {
    return { text: value ? 'true' : 'false', numeric: false, empty: false }
  }

  if (Array.isArray(value) || isPlainObject(value)) {
    const code = JSON.stringify(value, null, 2)
    return {
      text: code,
      title: code,
      numeric: false,
      empty: false,
      code,
    }
  }

  const text = String(value)
  const trimmed = text.trim()

  if (URL_RE.test(trimmed)) {
    return { text: trimmed, numeric: false, empty: false, href: trimmed }
  }

  if (ISO_DATE_ONLY.test(trimmed)) {
    const localized = formatDateOnly(trimmed)
    if (localized) {
      return { text: localized, title: trimmed, numeric: false, empty: false }
    }
  }

  if (ISO_DATE_TIME.test(trimmed)) {
    const parsed = new Date(trimmed)
    if (!Number.isNaN(parsed.getTime())) {
      return {
        text: parsed.toLocaleString(),
        title: trimmed,
        numeric: false,
        empty: false,
      }
    }
  }

  return {
    text,
    title: column ? `${column}: ${text}` : text,
    numeric: false,
    empty: false,
  }
}

/**
 * Every column present in the result, in first-seen order.
 *
 * Using only the first row's keys dropped columns from `UNION` results, where
 * each row may carry a different column set.
 */
export function collectColumns(rows: Record<string, unknown>[]): string[] {
  const seen = new Set<string>()
  const columns: string[] = []
  for (const row of rows) {
    for (const key of Object.keys(row ?? {})) {
      if (!seen.has(key)) {
        seen.add(key)
        columns.push(key)
      }
    }
  }
  return columns
}

/**
 * True when every non-empty value in the column is a number, so the column
 * can be right-aligned.
 */
export function isNumericColumn(rows: Record<string, unknown>[], column: string): boolean {
  let numeric = false
  for (const row of rows) {
    const value = row?.[column]
    if (value === null || value === undefined || value === '') continue
    if (typeof value !== 'number') return false
    numeric = true
  }
  return numeric
}
