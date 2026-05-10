import { useState } from 'react'
import { optimizeQuery } from '../api/dashboardapi'

interface ActiveConnection {
  id: number
  host: string
  database: string
  username: string
  tables: string[]
}

function SQLQueryOptimizer({ activeConnection }: { activeConnection: ActiveConnection | null }) {
  const [sentence, setSentence] = useState('')
  const [optimizedQuery, setOptimizedQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!sentence.trim()) {
      setError('Please enter a natural language sentence')
      return
    }

    try {
      setLoading(true)
      setError('')
      setSuccess(false)
      
      const response = await optimizeQuery(sentence, activeConnection?.id)
      
      if (response.data.success === false) {
        setError(response.data.error || 'Failed to optimize query')
        setOptimizedQuery('')
      } else {
        setOptimizedQuery(response.data.output_query)
        setSuccess(true)
      }
    } catch (err: any) {
      const errorMsg = err?.response?.data?.error || err?.response?.data?.message || 'Failed to optimize query'
      setError(errorMsg)
      setOptimizedQuery('')
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(optimizedQuery)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setError('Failed to copy to clipboard')
    }
  }

  const handleClear = () => {
    setSentence('')
    setOptimizedQuery('')
    setError('')
    setSuccess(false)
  }

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <div style={styles.headerIcon}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h5 style={styles.cardTitle}>SQL Query Optimizer</h5>
      </div>
      <div style={styles.cardBody}>
        {activeConnection ? (
          <div style={styles.connectionInfo}>
            <div style={styles.connectionHeader}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <ellipse cx="12" cy="5" rx="9" ry="3"/>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
              </svg>
              <span style={styles.connectionLabel}>Connected to {activeConnection.database}@{activeConnection.host}</span>
            </div>
            <div style={styles.tablesContainer}>
              <span style={styles.tablesLabel}>Tables:</span>
              <div style={styles.tablesList}>
                {activeConnection.tables.map((table) => (
                  <span key={table} style={styles.tableTag}>{table}</span>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div style={styles.noConnection}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>No database connected. Select a connection from Saved Connections.</span>
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div style={styles.formGroup}>
            <label htmlFor="sentence" style={styles.label}>
              Describe your query in natural language
            </label>
            <textarea
              id="sentence"
              style={styles.textarea}
              rows={3}
              placeholder="e.g., Get all active users created in the last 30 days..."
              value={sentence}
              onChange={(e) => setSentence(e.target.value)}
              disabled={loading}
            />
          </div>

          {error && (
            <div style={styles.errorAlert}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <span>{error}</span>
              <button type="button" style={styles.closeBtn} onClick={() => setError('')}>×</button>
            </div>
          )}

          {success && optimizedQuery && (
            <div style={styles.successAlert}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <span>Query optimized successfully!</span>
            </div>
          )}

          <div style={styles.buttonGroup}>
            <button
              type="submit"
              style={{...styles.button, ...styles.primaryButton, ...(loading ? styles.buttonDisabled : {})}}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span style={styles.spinner} />
                  Optimizing...
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                  </svg>
                  Optimize Query
                </>
              )}
            </button>
            {sentence && (
              <button
                type="button"
                style={{...styles.button, ...styles.secondaryButton}}
                onClick={handleClear}
                disabled={loading}
              >
                Clear
              </button>
            )}
          </div>
        </form>

        {optimizedQuery && (
          <div style={styles.resultSection}>
            <div style={styles.codeHeader}>
              <span style={styles.codeLabel}>SQL</span>
              <button
                type="button"
                style={{...styles.copyButton, ...(copied ? styles.copyButtonSuccess : {})}}
                onClick={handleCopy}
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <div style={styles.codeBlock}>
              <code style={styles.code}>{optimizedQuery}</code>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: 'rgba(26, 26, 46, 0.6)',
    borderRadius: '16px',
    border: '1px solid rgba(255,255,255,0.08)',
    overflow: 'hidden',
    backdropFilter: 'blur(12px)',
  },
  cardHeader: {
    background: 'linear-gradient(135deg, rgba(102, 126, 234, 0.2), rgba(118, 75, 162, 0.2))',
    padding: '20px 24px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  headerIcon: {
    width: '40px',
    height: '40px',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #667eea, #764ba2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#fff',
  },
  cardTitle: {
    margin: 0,
    color: '#ffffff',
    fontSize: '16px',
    fontWeight: 600,
  },
  cardBody: {
    padding: '24px',
  },
  formGroup: {
    marginBottom: '20px',
  },
  label: {
    display: 'block',
    color: '#b8b8d0',
    fontSize: '13px',
    fontWeight: 500,
    marginBottom: '8px',
  },
  textarea: {
    width: '100%',
    padding: '14px 16px',
    background: 'rgba(0,0,0,0.2)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '10px',
    color: '#ffffff',
    fontSize: '14px',
    fontFamily: 'inherit',
    resize: 'vertical',
    minHeight: '100px',
    outline: 'none',
    transition: 'all 0.2s',
  },
  errorAlert: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '12px 16px',
    background: 'rgba(239, 68, 68, 0.1)',
    border: '1px solid rgba(239, 68, 68, 0.2)',
    borderRadius: '8px',
    color: '#ef4444',
    fontSize: '13px',
    marginBottom: '16px',
  },
  successAlert: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '12px 16px',
    background: 'rgba(34, 197, 94, 0.1)',
    border: '1px solid rgba(34, 197, 94, 0.2)',
    borderRadius: '8px',
    color: '#22c55e',
    fontSize: '13px',
    marginBottom: '16px',
  },
  closeBtn: {
    marginLeft: 'auto',
    background: 'none',
    border: 'none',
    color: 'inherit',
    fontSize: '18px',
    cursor: 'pointer',
    padding: '0 4px',
  },
  buttonGroup: {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap' as const,
  },
  button: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    padding: '12px 24px',
    borderRadius: '10px',
    fontSize: '14px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s',
    border: 'none',
  },
  primaryButton: {
    flex: 1,
    background: 'linear-gradient(135deg, #667eea, #764ba2)',
    color: '#ffffff',
  },
  secondaryButton: {
    background: 'rgba(255,255,255,0.06)',
    color: '#b8b8d0',
    border: '1px solid rgba(255,255,255,0.1)',
  },
  buttonDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  spinner: {
    width: '16px',
    height: '16px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#ffffff',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  resultSection: {
    marginTop: '16px',
    paddingTop: '16px',
    borderTop: '1px solid rgba(255,255,255,0.06)',
  },
  codeHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '12px',
  },
  codeLabel: {
    color: '#667eea',
    fontSize: '12px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },
  copyButton: {
    padding: '4px 12px',
    background: 'transparent',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: '#8b8ba0',
    fontSize: '11px',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  copyButtonSuccess: {
    color: '#22c55e',
    borderColor: 'rgba(34, 197, 94, 0.4)',
  },
  codeBlock: {
    padding: '0 16px',
    overflow: 'auto',
  },
  code: {
    color: '#a5b4fc',
    fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
    fontSize: '14px',
    lineHeight: '1.7',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  connectionInfo: {
    padding: '16px',
    background: 'rgba(34, 197, 94, 0.08)',
    border: '1px solid rgba(34, 197, 94, 0.2)',
    borderRadius: '10px',
    marginBottom: '20px',
  },
  connectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '12px',
    color: '#22c55e',
    overflow: 'hidden',
  },
  connectionLabel: {
    fontSize: '13px',
    fontWeight: 600,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  tablesContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
  },
  tablesLabel: {
    fontSize: '12px',
    color: '#8b8ba0',
    fontWeight: 500,
  },
  tablesList: {
    display: 'flex',
    gap: '6px',
    flexWrap: 'wrap',
  },
  tableTag: {
    padding: '4px 10px',
    background: 'rgba(34, 197, 94, 0.12)',
    border: '1px solid rgba(34, 197, 94, 0.25)',
    borderRadius: '6px',
    color: '#22c55e',
    fontSize: '11px',
    fontWeight: 500,
  },
  noConnection: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '16px',
    background: 'rgba(239, 68, 68, 0.08)',
    border: '1px solid rgba(239, 68, 68, 0.2)',
    borderRadius: '10px',
    marginBottom: '20px',
    color: '#ef4444',
    fontSize: '13px',
  },
}

export default SQLQueryOptimizer
