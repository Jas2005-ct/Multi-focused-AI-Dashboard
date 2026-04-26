import { Navigate } from 'react-router-dom'
import { getToken } from '../api/authapi'
import type { ReactNode } from 'react'  // Add this import

type Props = {
  children: ReactNode  // Use ReactNode directly
}

function ProtectedRoute({ children }: Props) {
  return getToken() ? children : <Navigate to="/" />
}

export default ProtectedRoute