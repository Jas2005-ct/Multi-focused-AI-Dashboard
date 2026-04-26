import { useNavigate } from 'react-router-dom'
import { logoutUser } from '../api/authapi'

function Dashboard() {
  const navigate = useNavigate()

  const handleLogout = () => {
    logoutUser()
    navigate('/')
  }

  return (
    <div className="auth-container">
      <h1>Welcome to Dashboard</h1>
      <button onClick={handleLogout}>Logout</button>
    </div>
  )
}

export default Dashboard