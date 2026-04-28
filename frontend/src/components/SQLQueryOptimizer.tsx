import { useState } from 'react'
import { optimizeQuery } from '../api/dashboardapi'

function SQLQueryOptimizer() {
  const [sentence, setSentence] = useState('')
  const [optimizedQuery, setOptimizedQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

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
      
      const response = await optimizeQuery(sentence)
      setOptimizedQuery(response.data.output_query)
      setSuccess(true)
      
    } catch (err: any) {
      setError(err?.response?.data?.message || 'Failed to optimize query')
      setOptimizedQuery('')
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(optimizedQuery)
    alert('Query copied to clipboard!')
  }

  return (
    <div className="card mb-4 shadow-sm">
      <div className="card-header bg-primary text-white">
        <h5 className="mb-0">SQL Query Optimizer</h5>
      </div>
      <div className="card-body">
        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label htmlFor="sentence" className="form-label">
              Describe your query in natural language
            </label>
            <textarea
              id="sentence"
              className="form-control"
              rows={3}
              placeholder="e.g., Get all active users created in the last 30 days"
              value={sentence}
              onChange={(e) => setSentence(e.target.value)}
              disabled={loading}
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

          {success && optimizedQuery && (
            <div className="alert alert-success">
              Query optimized successfully!
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary w-100"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true" />
                Optimizing...
              </>
            ) : (
              'Optimize Query'
            )}
          </button>
        </form>

        {optimizedQuery && (
          <div className="mt-4">
            <h6 className="fw-bold mb-2">Optimized SQL Query:</h6>
            <div className="bg-light p-3 rounded border">
              <code className="text-dark" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {optimizedQuery}
              </code>
            </div>
            <button
              type="button"
              className="btn btn-outline-secondary btn-sm mt-2"
              onClick={handleCopy}
            >
              📋 Copy to Clipboard
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default SQLQueryOptimizer
