import { Navigate, useSearchParams } from 'react-router-dom'
import { useEffect } from 'react'
import { getToken, saveToken } from '../api/authapi'
import type { ReactNode } from 'react'

type Props = {
  children: ReactNode
}

function ProtectedRoute({ children }: Props) {
  const [searchParams, setSearchParams] = useSearchParams()
  
  // Handle Google OAuth token from URL
  useEffect(() => {
    const token = searchParams.get('token')
    if (token) {
      saveToken(token)
      // Remove token from URL without reloading
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])
  
  const token = getToken()
  if (!token) {
    return <Navigate to="/" />
  }
  
  return children
}

export default ProtectedRoute