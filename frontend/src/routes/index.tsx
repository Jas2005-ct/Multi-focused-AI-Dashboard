import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AuthLayout from '../components/layout/authLayout'
import AppLayout from '../components/layout/appLayout'
import Login from '../components/auth/login'
import Signup from '../components/auth/signIn'
import PrivateRoute from './PrivateRoute'
import PublicRoute from './PublicRoute'

const AppRoutes = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />

        <Route element={<PublicRoute />}>
          <Route element={<AuthLayout />}>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
          </Route>
        </Route>

        <Route element={<PrivateRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/app" element={<div>App pages will appear here.</div>} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default AppRoutes;