import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { loginUser, saveToken, saveUser } from '../api/authapi'
import ErrorModal from '../components/ErrorModal'

function Login() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    email: '',
    password: ''
  })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{title: string, message: string} | null>(null)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value })
    setError(null)
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.email || !form.password) {
      setError({ title: 'Missing Fields', message: 'Please fill in all fields' })
      return
    }
    try {
      setLoading(true)
      const res = await loginUser(form)
      saveToken(res.data.token)
      saveUser(res.data.user)
      navigate('/dashboard')
    } catch (err: any) {
      const errorTitle = err?.response?.data?.error || "Login Failed"
      const errorMessage = err?.response?.data?.message || "Something went wrong. Please try again."
      setError({ title: errorTitle, message: errorMessage })
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleRedirect = () => {
    window.location.href = `${import.meta.env.VITE_API_URL}/auth/login`
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <div style={styles.logo}>AI</div>
          <h1 style={styles.title}>Welcome Back</h1>
          <p style={styles.subtitle}>Sign in to your AI Dashboard</p>
        </div>

        <form onSubmit={handleLogin} style={styles.form}>
          <div style={styles.inputGroup}>
            <label style={styles.label}>Email</label>
            <input
              name="email"
              type="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              style={styles.input}
            />
          </div>

          <div style={styles.inputGroup}>
            <label style={styles.label}>Password</label>
            <input
              name="password"
              type="password"
              placeholder="Enter your password"
              value={form.password}
              onChange={handleChange}
              style={styles.input}
            />
            <div style={{ textAlign: 'right' as const }}>
              <Link to="/forgot-password" style={{ color: '#667eea', fontSize: '13px', textDecoration: 'none' }}>Forgot password?</Link>
            </div>
          </div>

          <button type="submit" disabled={loading} style={{
            ...styles.button,
            ...(loading ? styles.buttonDisabled : {})
          }}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div style={styles.divider}>
          <div style={styles.dividerLine}></div>
          <span style={styles.dividerText}>or</span>
          <div style={styles.dividerLine}></div>
        </div>

        <button onClick={handleGoogleRedirect} style={styles.googleButton}>
          <svg style={styles.googleIcon} viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Sign in with Google
        </button>

        <p style={styles.footer}>
          Don't have an account? <Link to="/register" style={styles.link}>Create one</Link>
        </p>
      </div>

      <ErrorModal
        isOpen={!!error}
        title={error?.title || ''}
        message={error?.message || ''}
        onClose={() => setError(null)}
      />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #0f0c29, #302b63, #24243e)',
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    padding: '20px',
    boxSizing: 'border-box',
  },
  card: {
    background: '#1a1a2e',
    borderRadius: '16px',
    padding: '48px 40px',
    width: '100%',
    maxWidth: '420px',
    boxShadow: '0 25px 50px rgba(0,0,0,0.4)',
    border: '1px solid rgba(255,255,255,0.05)',
    margin: '0',
  },
  header: {
    textAlign: 'center' as const,
    marginBottom: '32px',
  },
  logo: {
    width: '48px',
    height: '48px',
    borderRadius: '12px',
    background: 'linear-gradient(135deg, #667eea, #764ba2)',
    color: '#fff',
    fontSize: '20px',
    fontWeight: 700,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '16px',
  },
  title: {
    color: '#ffffff',
    fontSize: '28px',
    fontWeight: 700,
    margin: '0 0 8px 0',
  },
  subtitle: {
    color: '#8b8ba7',
    fontSize: '14px',
    margin: 0,
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '20px',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '6px',
  },
  label: {
    color: '#b8b8d0',
    fontSize: '13px',
    fontWeight: 500,
  },
  input: {
    background: '#16162a',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: '10px',
    padding: '12px 16px',
    color: '#ffffff',
    fontSize: '15px',
    outline: 'none',
    transition: 'border-color 0.2s',
  },
  button: {
    background: 'linear-gradient(135deg, #667eea, #764ba2)',
    color: '#fff',
    border: 'none',
    borderRadius: '10px',
    padding: '14px',
    fontSize: '16px',
    fontWeight: 600,
    cursor: 'pointer',
    marginTop: '4px',
    transition: 'opacity 0.2s',
  },
  buttonDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  error: {
    background: 'rgba(239,68,68,0.1)',
    border: '1px solid rgba(239,68,68,0.3)',
    color: '#ef4444',
    padding: '10px 14px',
    borderRadius: '8px',
    fontSize: '13px',
  },
  divider: {
    display: 'flex',
    alignItems: 'center',
    margin: '24px 0',
    position: 'relative' as const,
  },
  dividerText: {
    color: '#5a5a7a',
    fontSize: '13px',
    padding: '0 16px',
    background: '#1a1a2e',
    zIndex: 1,
  },
  dividerLine: {
    flex: 1,
    height: '1px',
    background: 'rgba(255,255,255,0.1)',
  },
  googleButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '10px',
    width: '100%',
    background: '#ffffff',
    border: 'none',
    borderRadius: '10px',
    padding: '12px',
    fontSize: '15px',
    fontWeight: 500,
    color: '#3c4043',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  googleIcon: {
    width: '20px',
    height: '20px',
  },
  footer: {
    textAlign: 'center' as const,
    color: '#8b8ba7',
    fontSize: '14px',
    marginTop: '24px',
  },
  link: {
    color: '#667eea',
    textDecoration: 'none',
    fontWeight: 500,
  },
}

export default Login