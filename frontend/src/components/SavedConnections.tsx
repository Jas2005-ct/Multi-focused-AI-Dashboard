import { useState, useEffect } from 'react'
import { getConnections, selectConnection, deleteConnection } from '../api/dashboardapi'

interface Connection {
  id: number
  host: string
  port: number
  database: string
  username: string
  created_at?: string
}

import type { ActiveConnection } from '../types/connection'

function SavedConnections({ onConnectionSelect }: { onConnectionSelect: (connection: ActiveConnection | null) => void }) {
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [activeConnectionId, setActiveConnectionId] = useState<number | null>(null)
  const [connectingId, setConnectingId] = useState<number | null>(null)

  useEffect(() => {
    loadConnections()
  }, [])

  const loadConnections = async () => {
    try {
      setLoading(true)
      const response = await getConnections()
      if (response.data.success) {
        setConnections(response.data.connections)
      } else {
        setMessage(response.data.message || 'Failed to load connections')
      }
    } catch (err: any) {
      setMessage(err?.response?.data?.message || 'Failed to load connections')
    } finally {
      setLoading(false)
    }
  }

  const handleConnect = async (dbId: number) => {
    try {
      setConnectingId(dbId)
      const response = await selectConnection(dbId)
      if (response.data.success) {
        setActiveConnectionId(dbId)
        onConnectionSelect({
          id: response.data.connection.id,
          host: response.data.connection.host,
          database: response.data.connection.database,
          username: response.data.connection.username,
          tables: response.data.tables
        })
        setMessage('')
      } else {
        setMessage(response.data.message || 'Connection failed')
      }
    } catch (err: any) {
      setMessage(err?.response?.data?.message || 'Connection failed')
    } finally {
      setConnectingId(null)
    }
  }

  const handleDelete = async (dbId: number) => {
    try {
      const response = await deleteConnection(dbId)
      if (response.data.success) {
        if (activeConnectionId === dbId) {
          setActiveConnectionId(null)
          onConnectionSelect(null)
        }
        loadConnections()
        setMessage('Connection deleted')
      } else {
        setMessage(response.data.message || 'Failed to delete')
      }
    } catch (err: any) {
      setMessage(err?.response?.data?.message || 'Failed to delete')
    }
  }

  if (loading) {
    return (
      <div style={styles.card}>
        <div style={styles.cardHeader}>
          <div style={{...styles.headerIcon, background: 'linear-gradient(135deg, #06b6d4, #0891b2)'}}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
          </div>
          <h5 style={styles.cardTitle}>Saved Database Connections</h5>
        </div>
        <div style={{...styles.cardBody, textAlign: 'center', padding: '48px'}}>
          <span style={styles.spinner} />
          <p style={{color: '#8b8ba7', marginTop: '16px'}}>Loading connections...</p>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <div style={{...styles.headerIcon, background: 'linear-gradient(135deg, #06b6d4, #0891b2)'}}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
        </div>
        <h5 style={styles.cardTitle}>Saved Database Connections</h5>
        <span style={styles.badge}>{connections.length}</span>
      </div>
      <div style={styles.cardBody}>
        {message && (
          <div style={styles.infoAlert}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="16" x2="12" y2="12"/>
              <line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
            <span>{message}</span>
            <button type="button" style={styles.closeBtn} onClick={() => setMessage('')}>×</button>
          </div>
        )}

        {connections.length === 0 ? (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <ellipse cx="12" cy="5" rx="9" ry="3"/>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
              </svg>
            </div>
            <p style={styles.emptyText}>No saved database connections yet</p>
            <p style={styles.emptySubtext}>Add one using the connection form</p>
          </div>
        ) : (
          <div style={styles.tableContainer}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Host</th>
                  <th style={styles.th}>Port</th>
                  <th style={styles.th}>Database</th>
                  <th style={styles.th}>Username</th>
                  <th style={{...styles.th, width: '120px'}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((conn) => (
                  <tr key={conn.id} style={styles.tr}>
                    <td style={styles.td}>{conn.host}</td>
                    <td style={styles.td}>{conn.port}</td>
                    <td style={styles.td}>{conn.database}</td>
                    <td style={styles.td}>{conn.username}</td>
                    <td style={styles.td}>
                      <div style={{display: 'flex', gap: '8px'}}>
                        {activeConnectionId === conn.id ? (
                          <span style={styles.activeBadge}>Active</span>
                        ) : (
                          <button
                            style={styles.connectBtn}
                            onClick={() => handleConnect(conn.id)}
                            disabled={connectingId === conn.id}
                          >
                            {connectingId === conn.id ? 'Connecting...' : 'Connect'}
                          </button>
                        )}
                        <button
                          style={styles.deleteBtn}
                          onClick={() => handleDelete(conn.id)}
                          title="Delete connection"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div style={styles.footerNote}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <span>Connection details are stored securely on the server. Passwords are encrypted.</span>
        </div>
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
    background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(8, 145, 178, 0.2))',
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
    flex: 1,
  },
  badge: {
    padding: '4px 12px',
    background: 'rgba(6, 182, 212, 0.2)',
    border: '1px solid rgba(6, 182, 212, 0.3)',
    borderRadius: '20px',
    color: '#06b6d4',
    fontSize: '13px',
    fontWeight: 600,
  },
  cardBody: {
    padding: '24px',
  },
  spinner: {
    display: 'inline-block',
    width: '32px',
    height: '32px',
    border: '3px solid rgba(255,255,255,0.1)',
    borderTopColor: '#06b6d4',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  infoAlert: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '12px 16px',
    background: 'rgba(6, 182, 212, 0.1)',
    border: '1px solid rgba(6, 182, 212, 0.2)',
    borderRadius: '8px',
    color: '#06b6d4',
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
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '48px 24px',
    textAlign: 'center',
  },
  emptyIcon: {
    color: '#4b5563',
    marginBottom: '16px',
  },
  emptyText: {
    color: '#8b8ba7',
    fontSize: '15px',
    fontWeight: 500,
    margin: '0 0 4px 0',
  },
  emptySubtext: {
    color: '#6b7280',
    fontSize: '13px',
    margin: 0,
  },
  tableContainer: {
    overflowX: 'auto' as const,
    maxWidth: '100%',
    borderRadius: '10px',
    border: '1px solid rgba(255,255,255,0.06)',
    marginBottom: '16px',
    WebkitOverflowScrolling: 'touch',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '13px',
  },
  th: {
    padding: '14px 16px',
    background: 'rgba(0,0,0,0.3)',
    color: '#b8b8d0',
    fontWeight: 600,
    textAlign: 'left',
    fontSize: '12px',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  tr: {
    borderBottom: '1px solid rgba(255,255,255,0.04)',
  },
  td: {
    padding: '14px 16px',
    color: '#e5e7eb',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: '13px',
    maxWidth: '200px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  deleteBtn: {
    background: 'none',
    border: 'none',
    color: '#6b7280',
    cursor: 'pointer',
    padding: '6px',
    borderRadius: '6px',
    transition: 'all 0.2s',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  connectBtn: {
    padding: '6px 12px',
    background: 'rgba(6, 182, 212, 0.15)',
    border: '1px solid rgba(6, 182, 212, 0.3)',
    borderRadius: '6px',
    color: '#06b6d4',
    fontSize: '12px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  activeBadge: {
    padding: '6px 12px',
    background: 'rgba(34, 197, 94, 0.15)',
    border: '1px solid rgba(34, 197, 94, 0.3)',
    borderRadius: '6px',
    color: '#22c55e',
    fontSize: '12px',
    fontWeight: 600,
  },
  footerNote: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '12px 16px',
    background: 'rgba(0,0,0,0.2)',
    borderRadius: '8px',
    color: '#6b7280',
    fontSize: '12px',
  },
}

export default SavedConnections
