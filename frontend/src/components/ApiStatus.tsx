import { useEffect, useState } from 'react'
import { apiStatus } from '../api/dashboardapi'

type Status = 'checking' | 'ok' | 'down'

function ApiStatus() {
  const [status, setStatus] = useState<Status>('checking')

  useEffect(() => {
    let mounted = true
    apiStatus()
      .then((res) => {
        if (mounted) setStatus(res.data?.status === 'ok' ? 'ok' : 'down')
      })
      .catch(() => {
        if (mounted) setStatus('down')
      })
    return () => {
      mounted = false
    }
  }, [])

  const color =
    status === 'ok' ? '#22c55e' : status === 'checking' ? '#8b8ba7' : '#ef4444'
  const label =
    status === 'ok'
      ? 'API connected'
      : status === 'checking'
        ? 'Checking API…'
        : 'API unreachable'

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
      <span
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: color,
        }}
      />
      <span>{label}</span>
    </span>
  )
}

export default ApiStatus
