import type { CSSProperties } from 'react'
import type { AnswerRow } from '../types/answer'
import { collectColumns, formatCell, isNumericColumn } from '../utils/format'

interface ResultTableProps {
  rows: AnswerRow[]
  /** Total matching rows, when the agent also ran a count. */
  total?: number | null
  /** Source table name, shown as a caption. */
  table?: string | null
}

/**
 * Renders the rows the agent fetched.
 *
 * The agent used to return prose only, so the model had to re-type the rows
 * into a markdown table inside its answer — lossy, and unreadable at narrow
 * widths. The rows themselves arrive as structured data, so they are rendered
 * here instead.
 */
function ResultTable({ rows, total, table }: ResultTableProps) {
  if (!rows || rows.length === 0) return null

  const columns = collectColumns(rows)
  const numericColumns = new Set(
    columns.filter((column) => isNumericColumn(rows, column)),
  )

  return (
    <div style={styles.wrap}>
      <div style={styles.header}>
        {table ? <span style={styles.tableName}>{table}</span> : <span />}
        <span style={styles.meta}>
          {typeof total === 'number' && total > rows.length
            ? `Showing ${rows.length} of ${total.toLocaleString()}`
            : `${rows.length.toLocaleString()} row${rows.length === 1 ? '' : 's'}`}
        </span>
      </div>
      <div style={styles.scroll}>
        <table style={styles.table}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  style={{
                    ...styles.th,
                    textAlign: numericColumns.has(column) ? 'right' : 'left',
                  }}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} style={index % 2 === 1 ? styles.rowAlt : undefined}>
                {columns.map((column) => {
                  const cell = formatCell(row?.[column], column)
                  return (
                    <td
                      key={column}
                      title={cell.title}
                      style={{
                        ...styles.td,
                        textAlign: numericColumns.has(column) ? 'right' : 'left',
                        ...(cell.empty ? styles.tdEmpty : null),
                      }}
                    >
                      {cell.href ? (
                        <a
                          href={cell.href}
                          target="_blank"
                          rel="noreferrer noopener"
                          style={styles.link}
                        >
                          {cell.text}
                        </a>
                      ) : cell.code ? (
                        <code style={styles.code}>{cell.text}</code>
                      ) : (
                        cell.text
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    borderRadius: '8px',
    border: '1px solid rgba(255,255,255,0.08)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    padding: '8px 12px',
    background: 'rgba(0,0,0,0.25)',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  tableName: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#a5b4fc',
    fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
  },
  meta: {
    fontSize: '11px',
    color: '#8b8ba0',
    whiteSpace: 'nowrap',
  },
  scroll: {
    overflow: 'auto',
    maxHeight: '320px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '12px',
  },
  th: {
    position: 'sticky',
    top: 0,
    zIndex: 1,
    background: 'rgba(30, 30, 52, 0.98)',
    color: '#b8b8d0',
    padding: '8px 12px',
    fontWeight: 600,
    borderBottom: '1px solid rgba(255,255,255,0.12)',
    whiteSpace: 'nowrap',
  },
  rowAlt: {
    background: 'rgba(255,255,255,0.02)',
  },
  td: {
    padding: '8px 12px',
    color: '#e0e7ff',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
    maxWidth: '320px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    verticalAlign: 'top',
  },
  tdEmpty: {
    color: '#5c5c78',
  },
  link: {
    color: '#7dd3fc',
    textDecoration: 'underline',
  },
  code: {
    display: 'block',
    fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
    fontSize: '11px',
    color: '#c4b5fd',
    whiteSpace: 'pre-wrap',
    // Clamp so one deeply-nested JSON column cannot stretch the whole row.
    maxHeight: '80px',
    overflow: 'auto',
  },
}

export default ResultTable
