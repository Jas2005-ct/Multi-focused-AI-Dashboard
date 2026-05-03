import { useState } from 'react'
import { saveDBConnection } from '../api/dashboardapi'

interface ConnectionData {
  host: string
  port: number
  database: string
  username: string
  password: string
  connection_string?: string
}

function DBConnectionForm() {
  const [formData, setFormData] = useState<ConnectionData>({
    host: 'localhost',
    port: 5432,
    database: '',
    username: '',
    password: '',
    connection_string: ''
  })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData({
      ...formData,
      [name]: name === 'port' ? parseInt(value) : value
    })
  }

  const validateForm = (): boolean => {
    if (!formData.host.trim()) {
      setError('Host is required')
      return false
    }
    if (!formData.database.trim()) {
      setError('Database name is required')
      return false
    }
    if (!formData.username.trim()) {
      setError('Username is required')
      return false
    }
    if (!formData.password.trim()) {
      setError('Password is required')
      return false
    }
    if (formData.port < 1 || formData.port > 65535) {
      setError('Port must be between 1 and 65535')
      return false
    }
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!validateForm()) {
      return
    }

    try {
      setLoading(true)
      setError('')
      setSuccess(false)

      const response = await saveDBConnection(formData)
      setSuccessMessage(response.data.message)
      setSuccess(true)

      // Save to localStorage for client-side display
      try {
        const saved = localStorage.getItem('dbConnections')
        const connections = saved ? JSON.parse(saved) : []
        const newConnection = {
          id: Date.now(),
          host: formData.host,
          port: formData.port,
          database: formData.database,
          username: formData.username
        }
        connections.push(newConnection)
        localStorage.setItem('dbConnections', JSON.stringify(connections))
        
        // Dispatch custom event to notify SavedConnections component
        window.dispatchEvent(new Event('connectionAdded'))
      } catch (storageErr) {
        console.error('Failed to save to localStorage:', storageErr)
      }

      // Reset form
      setFormData({
        host: 'localhost',
        port: 5432,
        database: '',
        username: '',
        password: '',
        connection_string: ''
      })

    } catch (err: any) {
      const errMessage = err?.response?.data?.message || err?.response?.data?.error || 'Failed to save connection'
      setError(errMessage)
      setSuccess(false)
    } finally {
      setLoading(false)
    }
  }

  const inputFields = [
    { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
    { name: 'port', label: 'Port', type: 'number', placeholder: '5432', required: true },
    { name: 'database', label: 'Database Name', type: 'text', placeholder: 'mydb', required: true },
    { name: 'username', label: 'Username', type: 'text', placeholder: 'postgres', required: true },
    { name: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: true },
  ]

  const styles: Record<string, React.CSSProperties> = {
    card: {
      background: 'rgba(26, 26, 46, 0.6)',
      borderRadius: '16px',
      border: '1px solid rgba(255,255,255,0.08)',
      overflow: 'hidden',
      backdropFilter: 'blur(12px)',
    },
    cardHeader: {
      background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.2))',
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
    grid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: '16px',
    },
    formGroup: {
      marginBottom: '16px',
    },
    label: {
      display: 'block',
      color: '#b8b8d0',
      fontSize: '13px',
      fontWeight: 500,
      marginBottom: '8px',
    },
    input: {
      width: '100%',
      padding: '12px 14px',
      background: 'rgba(0,0,0,0.2)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: '10px',
      color: '#ffffff',
      fontSize: '14px',
      fontFamily: 'inherit',
      outline: 'none',
      transition: 'all 0.2s',
      boxSizing: 'border-box',
    },
    hint: {
      display: 'block',
      color: '#6b7280',
      fontSize: '12px',
      marginTop: '6px',
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
    button: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '8px',
      width: '100%',
      padding: '14px 24px',
      borderRadius: '10px',
      fontSize: '14px',
      fontWeight: 500,
      cursor: 'pointer',
      transition: 'all 0.2s',
      border: 'none',
    },
    successButton: {
      background: 'linear-gradient(135deg, #10b981, #059669)',
      color: '#ffffff',
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
  }

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <div style={{...styles.headerIcon, background: 'linear-gradient(135deg, #10b981, #059669)'}}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
        </div>
        <h5 style={styles.cardTitle}>Database Connection</h5>
      </div>
      <div style={styles.cardBody}>
        <form onSubmit={handleSubmit}>
          <div style={styles.grid}>
            {inputFields.map((field) => (
              <div key={field.name} style={styles.formGroup}>
                <label htmlFor={field.name} style={styles.label}>
                  {field.label} {field.required && <span style={{color: '#ef4444'}}>*</span>}
                </label>
                <input
                  type={field.type}
                  id={field.name}
                  name={field.name}
                  value={formData[field.name as keyof ConnectionData]}
                  onChange={handleChange}
                  disabled={loading}
                  placeholder={field.placeholder}
                  style={styles.input}
                  min={field.type === 'number' ? 1 : undefined}
                  max={field.type === 'number' ? 65535 : undefined}
                />
              </div>
            ))}
          </div>

          <div style={styles.formGroup}>
            <label htmlFor="connection_string" style={styles.label}>
              Connection String (Optional)
            </label>
            <input
              type="text"
              id="connection_string"
              name="connection_string"
              value={formData.connection_string}
              onChange={handleChange}
              disabled={loading}
              placeholder="postgresql://user:password@host:port/database"
              style={styles.input}
            />
            <span style={styles.hint}>Leave empty to use individual fields above</span>
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

          {success && (
            <div style={styles.successAlert}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <span>{successMessage || 'Connection saved successfully!'}</span>
              <button type="button" style={styles.closeBtn} onClick={() => setSuccess(false)}>×</button>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{...styles.button, ...styles.successButton, ...(loading ? styles.buttonDisabled : {})}}
          >
            {loading ? (
              <><span style={styles.spinner} />Saving...</>
            ) : (
              <><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/>
                <polyline points="7 3 7 8 15 8"/>
              </svg>Save Connection</>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

export default DBConnectionForm
