import { Outlet, Navigate } from 'react-router-dom'

const isAuthenticated = false

const PrivateRoute = () => {
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />
}

export default PrivateRoute;
