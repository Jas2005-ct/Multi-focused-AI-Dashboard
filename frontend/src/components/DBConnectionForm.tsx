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

  return (
    <div className="card mb-4 shadow-sm">
      <div className="card-header bg-success text-white">
        <h5 className="mb-0">Database Connection</h5>
      </div>
      <div className="card-body">
        <form onSubmit={handleSubmit}>
          <div className="row">
            <div className="col-md-6 mb-3">
              <label htmlFor="host" className="form-label">
                Host <span className="text-danger">*</span>
              </label>
              <input
                type="text"
                id="host"
                className="form-control"
                name="host"
                value={formData.host}
                onChange={handleChange}
                disabled={loading}
              />
            </div>

            <div className="col-md-6 mb-3">
              <label htmlFor="port" className="form-label">
                Port <span className="text-danger">*</span>
              </label>
              <input
                type="number"
                id="port"
                className="form-control"
                name="port"
                value={formData.port}
                onChange={handleChange}
                disabled={loading}
                min="1"
                max="65535"
              />
            </div>
          </div>

          <div className="row">
            <div className="col-md-6 mb-3">
              <label htmlFor="database" className="form-label">
                Database Name <span className="text-danger">*</span>
              </label>
              <input
                type="text"
                id="database"
                className="form-control"
                name="database"
                value={formData.database}
                onChange={handleChange}
                disabled={loading}
              />
            </div>

            <div className="col-md-6 mb-3">
              <label htmlFor="username" className="form-label">
                Username <span className="text-danger">*</span>
              </label>
              <input
                type="text"
                id="username"
                className="form-control"
                name="username"
                value={formData.username}
                onChange={handleChange}
                disabled={loading}
              />
            </div>
          </div>

          <div className="mb-3">
            <label htmlFor="password" className="form-label">
              Password <span className="text-danger">*</span>
            </label>
            <input
              type="password"
              id="password"
              className="form-control"
              name="password"
              value={formData.password}
              onChange={handleChange}
              disabled={loading}
            />
          </div>

          <div className="mb-3">
            <label htmlFor="connection_string" className="form-label">
              Connection String (Optional)
            </label>
            <input
              type="text"
              id="connection_string"
              className="form-control"
              name="connection_string"
              value={formData.connection_string}
              onChange={handleChange}
              disabled={loading}
              placeholder="postgresql://user:password@host:port/database"
            />
          </div>

          {error && (
            <div className="alert alert-danger alert-dismissible fade show" role="alert">
              {error}
              <button
                type="button"
                className="btn-close"
                onClick={() => setError('')}
              />
            </div>
          )}

          {success && (
            <div className="alert alert-success alert-dismissible fade show" role="alert">
              ✓ {successMessage}
              <button
                type="button"
                className="btn-close"
                onClick={() => setSuccess(false)}
              />
            </div>
          )}

          <button
            type="submit"
            className="btn btn-success w-100"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true" />
                Saving...
              </>
            ) : (
              'Save Connection'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

export default DBConnectionForm
