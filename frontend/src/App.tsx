import { Navigate, Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AUTH_REQUIRED } from './config'
import ProtectedRoute from './routes/protectedroutes'

const Login = lazy(() => import('./pages/login'))
const Register = lazy(() => import('./pages/register'))
const Dashboard = lazy(() => import('./pages/dashboard'))
const ForgotPassword = lazy(() => import('./pages/forgotpassword'))

// Themed loader shown while lazy page chunks are downloading.
function AppLoader() {
  return (
    <div style={loaderStyles.overlay}>
      <div style={loaderStyles.logo}>AI</div>
      <div style={loaderStyles.ring} />
      <p style={loaderStyles.text}>Loading your workspace…</p>
    </div>
  )
}

const loaderStyles: Record<string, React.CSSProperties> = {
  overlay: {
    minHeight: '100svh',
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    gap: '20px',
    background: 'linear-gradient(135deg, #0f0c29, #302b63, #24243e)',
  },
  logo: {
    width: '56px',
    height: '56px',
    borderRadius: '14px',
    background: 'linear-gradient(135deg, #667eea, #764ba2)',
    color: '#fff',
    fontSize: '22px',
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    animation: 'app-pulse 1.6s ease-in-out infinite',
  },
  ring: {
    width: '34px',
    height: '34px',
    borderRadius: '50%',
    border: '3px solid rgba(255,255,255,0.12)',
    borderTopColor: '#667eea',
    animation: 'spin 0.9s linear infinite',
  },
  text: {
    color: '#8b8ba7',
    fontSize: '14px',
    margin: 0,
  },
}

function App() {
  return (
    <Suspense fallback={<AppLoader />}>
      <Routes>
        {/* TEMPORARY DEMO MODE: visitors go straight to the dashboard instead
            of the login screen. TODO: restore element={<Login />} and set
            AUTH_REQUIRED=true to re-enable login. */}
        <Route
          path="/"
          element={AUTH_REQUIRED ? <Login /> : <Navigate to="/dashboard" replace />}
        />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/dashboard" element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        } />
        <Route path="*" element={<div style={{ color: '#fff', textAlign: 'center', padding: 40 }}>404 - Page not found</div>} />
      </Routes>
    </Suspense>
  )
}

export default App
