import { useState, useEffect } from 'react'

interface Connection {
  id: number
  host: string
  port: number
  database: string
  username: string
}

function SavedConnections() {
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  useEffect(() => {
    loadConnections()
    
    // Listen for storage changes
    const handleStorageChange = () => {
      loadConnections()
    }

    window.addEventListener('storage', handleStorageChange)
    
    // Also listen for custom event from DBConnectionForm
    const handleConnectionAdded = () => {
      setTimeout(() => loadConnections(), 100)
    }
    window.addEventListener('connectionAdded', handleConnectionAdded as EventListener)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      window.removeEventListener('connectionAdded', handleConnectionAdded as EventListener)
    }
  }, [])

  const loadConnections = () => {
    try {
      const saved = localStorage.getItem('dbConnections')
      if (saved) {
        setConnections(JSON.parse(saved))
      } else {
        setConnections([])
      }
    } catch (err) {
      console.error('Failed to load connections:', err)
      setConnections([])
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="card shadow-sm">
        <div className="card-header bg-info text-white">
          <h5 className="mb-0">Saved Database Connections</h5>
        </div>
        <div className="card-body text-center">
          <div className="spinner-border" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card shadow-sm">
      <div className="card-header bg-info text-white">
        <h5 className="mb-0">Saved Database Connections</h5>
      </div>
      <div className="card-body">
        {message && (
          <div className="alert alert-info alert-dismissible fade show" role="alert">
            {message}
            <button
              type="button"
              className="btn-close"
              onClick={() => setMessage('')}
            />
          </div>
        )}

        {connections.length === 0 ? (
          <p className="text-muted text-center py-4">
            No saved database connections yet. Add one using the form above.
          </p>
        ) : (
          <div className="table-responsive">
            <table className="table table-hover mb-0">
              <thead className="table-light">
                <tr>
                  <th>Host</th>
                  <th>Port</th>
                  <th>Database</th>
                  <th>Username</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((conn) => (
                  <tr key={conn.id}>
                    <td className="font-monospace">{conn.host}</td>
                    <td className="font-monospace">{conn.port}</td>
                    <td className="font-monospace">{conn.database}</td>
                    <td className="font-monospace">{conn.username}</td>
                    <td>
                      <span className="badge bg-success">✓ Saved</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-3 text-muted small">
          <p>
            <strong>Note:</strong> Connection details are stored securely on the server. 
            Passwords are not displayed for security reasons.
          </p>
        </div>
      </div>
    </div>
  )
}

export default SavedConnections
