import { Navigate, useSearchParams } from 'react-router-dom'
import { useEffect } from 'react'
import { getToken, saveToken, saveUser } from '../api/authapi'
import type { ReactNode } from 'react'

type Props = {
  children: ReactNode
}

function ProtectedRoute({ children }: Props) {
  const [searchParams, setSearchParams] = useSearchParams()
  
  // Handle Google OAuth token and user from URL
  useEffect(() => {
    const token = searchParams.get('token')
    const userParam = searchParams.get('user')
    if (token) {
      saveToken(token)
      if (userParam) {
        try {
          const user = JSON.parse(decodeURIComponent(userParam))
          saveUser(user)
        } catch {
          // ignore invalid user data
        }
      }
      // Remove token and user from URL without reloading
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