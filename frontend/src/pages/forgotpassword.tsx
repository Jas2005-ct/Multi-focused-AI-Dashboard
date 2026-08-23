import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { forgotPassword, verifyOtp, resetPassword } from '../api/authapi'
import ErrorModal from '../components/ErrorModal'

function ForgotPassword() {
  const navigate = useNavigate()
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ title: string; message: string } | null>(null)
  const [info, setInfo] = useState('')

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return setError({ title: 'Missing email', message: 'Enter your email' })
    setLoading(true)
    setError(null)
    try {
      await forgotPassword(email)
      setInfo('OTP sent — check Flask terminal (dev) / email (prod). Valid 5 min.')
      setStep(2)
    } catch (err: any) {
      setError({ title: err?.response?.data?.error || 'Failed', message: err?.response?.data?.message || 'Try again' })
    } finally { setLoading(false) }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!otp) return setError({ title: 'Missing OTP', message: 'Enter 6-digit OTP' })
    setLoading(true)
    setError(null)
    try {
      await verifyOtp(email, otp)
      setInfo('OTP verified — set new password')
      setStep(3)
    } catch (err: any) {
      setError({ title: err?.response?.data?.error || 'Invalid OTP', message: err?.response?.data?.message || 'Try again' })
    } finally { setLoading(false) }
  }

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newPassword) return setError({ title: 'Missing password', message: 'Enter new password (8+ chars, upper/lower/digit)' })
    setLoading(true)
    setError(null)
    try {
      await resetPassword(email, otp, newPassword)
      setInfo('Password changed — redirecting to login…')
      setTimeout(() => navigate('/'), 1200)
    } catch (err: any) {
      setError({ title: err?.response?.data?.error || 'Reset failed', message: err?.response?.data?.message || 'Try again' })
    } finally { setLoading(false) }
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <div style={styles.logo}>AI</div>
          <h1 style={styles.title}>Reset Password</h1>
          <p style={styles.subtitle}>
            {step === 1 && 'Enter email to receive OTP'}
            {step === 2 && `OTP sent to ${email}`}
            {step === 3 && 'Enter new password'}
          </p>
        </div>

        {info && <div style={styles.info}>{info}</div>}

        {step === 1 && (
          <form onSubmit={handleForgot} style={styles.form}>
            <div style={styles.inputGroup}>
              <label style={styles.label}>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" style={styles.input} />
            </div>
            <button type="submit" disabled={loading} style={{ ...styles.button, ...(loading ? styles.buttonDisabled : {}) }}>
              {loading ? 'Sending...' : 'Send OTP'}
            </button>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={handleVerify} style={styles.form}>
            <div style={styles.inputGroup}>
              <label style={styles.label}>6-digit OTP (check Flask terminal)</label>
              <input value={otp} onChange={e => setOtp(e.target.value)} placeholder="123456" maxLength={6} style={styles.input} />
            </div>
            <button type="submit" disabled={loading} style={{ ...styles.button, ...(loading ? styles.buttonDisabled : {}) }}>
              {loading ? 'Verifying...' : 'Verify OTP'}
            </button>
            <button type="button" onClick={() => setStep(1)} style={styles.linkBtn}>Resend / change email</button>
          </form>
        )}

        {step === 3 && (
          <form onSubmit={handleReset} style={styles.form}>
            <div style={styles.inputGroup}>
              <label style={styles.label}>New Password</label>
              <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="NewPass123" style={styles.input} />
              <span style={styles.hint}>8+ chars, upper + lower + digit</span>
            </div>
            <button type="submit" disabled={loading} style={{ ...styles.button, ...(loading ? styles.buttonDisabled : {}) }}>
              {loading ? 'Saving...' : 'Change Password'}
            </button>
          </form>
        )}

        <p style={styles.footer}><Link to="/" style={styles.link}>Back to login</Link></p>
      </div>

      <ErrorModal isOpen={!!error} title={error?.title || ''} message={error?.message || ''} onClose={() => setError(null)} />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #0f0c29, #302b63, #24243e)', fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif", padding: '20px', boxSizing: 'border-box' },
  card: { background: '#1a1a2e', borderRadius: '16px', padding: '48px 40px', width: '100%', maxWidth: '420px', boxShadow: '0 25px 50px rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.05)' },
  header: { textAlign: 'center' as const, marginBottom: '32px' },
  logo: { width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #667eea, #764ba2)', color: '#fff', fontSize: '20px', fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: '16px' },
  title: { color: '#ffffff', fontSize: '28px', fontWeight: 700, margin: '0 0 8px 0' },
  subtitle: { color: '#8b8ba7', fontSize: '14px', margin: 0 },
  info: { background: 'rgba(102,126,234,0.15)', border: '1px solid rgba(102,126,234,0.3)', color: '#a5b4fc', padding: '10px 14px', borderRadius: '8px', fontSize: '13px', marginBottom: '16px' },
  form: { display: 'flex', flexDirection: 'column' as const, gap: '20px' },
  inputGroup: { display: 'flex', flexDirection: 'column' as const, gap: '6px' },
  label: { color: '#b8b8d0', fontSize: '13px', fontWeight: 500 },
  input: { background: '#16162a', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '12px 16px', color: '#ffffff', fontSize: '15px', outline: 'none' },
  hint: { color: '#5a5a7a', fontSize: '12px' },
  button: { background: 'linear-gradient(135deg, #667eea, #764ba2)', color: '#fff', border: 'none', borderRadius: '10px', padding: '14px', fontSize: '16px', fontWeight: 600, cursor: 'pointer', marginTop: '4px' },
  buttonDisabled: { opacity: 0.6, cursor: 'not-allowed' as const },
  linkBtn: { background: 'none', border: 'none', color: '#667eea', cursor: 'pointer', fontSize: '13px', marginTop: '4px' },
  footer: { textAlign: 'center' as const, color: '#8b8ba7', fontSize: '14px', marginTop: '24px' },
  link: { color: '#667eea', textDecoration: 'none', fontWeight: 500 },
}

export default ForgotPassword
