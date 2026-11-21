import { Navigate, useSearchParams } from 'react-router-dom'
import { useEffect } from 'react'
import { ensureDemoUser, getToken, saveToken, saveUser } from '../api/authapi'
import { AUTH_REQUIRED } from '../config'
import type { AuthUser } from '../types/auth'
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
        let user: AuthUser | null = null
        try {
          // searchParams.get() already URL-decodes once, so parse raw first —
          // a second decodeURIComponent throws "malformed URI" on names
          // containing '%' and would silently drop the user (same as
          // dashboard.tsx). Fallback covers older raw-encoded parameters.
          user = JSON.parse(userParam) as AuthUser
        } catch {
          try {
            user = JSON.parse(decodeURIComponent(userParam)) as AuthUser
          } catch {
            // ignore invalid user data — 'user' stays null from the declaration
          }
        }
        if (user && user.email) saveUser(user)
      }
      // Remove token and user from URL without reloading
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])
  
  // TEMPORARY DEMO MODE: skip the token check entirely so visitors land on
  // the dashboard without signing in. TODO: remove this branch (and set
  // AUTH_REQUIRED=true) to re-enable login.
  if (!AUTH_REQUIRED) {
    ensureDemoUser()
    return children
  }

  const token = getToken()
  if (!token) {
    return <Navigate to="/" />
  }
  
  return children
}

export default ProtectedRoute