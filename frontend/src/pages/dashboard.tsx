import { useNavigate } from 'react-router-dom'
import { logoutUser } from '../api/authapi'
import SQLQueryOptimizer from '../components/SQLQueryOptimizer'
import DBConnectionForm from '../components/DBConnectionForm'
import SavedConnections from '../components/SavedConnections'

function Dashboard() {
  const navigate = useNavigate()

  const handleLogout = () => {
    logoutUser()
    navigate('/')
  }

  return (
    <div className="dashboard-container">
      {/* Navbar Header */}
      <nav className="navbar navbar-dark bg-dark sticky-top shadow-sm mb-4">
        <div className="container-fluid">
          <span className="navbar-brand mb-0 h1">
            🚀 SQL Optimizer Dashboard
          </span>
          <button
            className="btn btn-outline-light"
            onClick={handleLogout}
          >
            Logout
          </button>
        </div>
      </nav>

      {/* Main Container */}
      <div className="container py-4">
        {/* Welcome Section */}
        <div className="mb-4">
          <h2 className="text-dark mb-2">Welcome to AI Dashboard</h2>
          <p className="text-muted">
            Optimize your SQL queries using natural language and manage your database connections.
          </p>
        </div>

        {/* Main Row */}
        <div className="row">
          {/* Left Column - Forms */}
          <div className="col-lg-6 mb-4">
            {/* SQL Query Optimizer */}
            <SQLQueryOptimizer />

            {/* Database Connection Form */}
            <DBConnectionForm />
          </div>

          {/* Right Column - Saved Connections */}
          <div className="col-lg-6">
            <SavedConnections />
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-light text-center text-muted py-4 mt-5 border-top">
        <p className="mb-0">
          © 2026 AI Dashboard. Powered by Flask & React
        </p>
      </footer>
    </div>
  )
}

export default Dashboard