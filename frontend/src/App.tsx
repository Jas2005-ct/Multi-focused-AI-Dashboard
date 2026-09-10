import { Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import ProtectedRoute from './routes/protectedroutes'

const Login = lazy(() => import('./pages/login'))
const Register = lazy(() => import('./pages/register'))
const Dashboard = lazy(() => import('./pages/dashboard'))
const ForgotPassword = lazy(() => import('./pages/forgotpassword'))

function App() {
  return (
    <Suspense fallback={<div style={{ color: '#fff', textAlign: 'center', padding: 40 }}>Loading...</div>}>
      <Routes>
        <Route path="/" element={<Login />} />
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
