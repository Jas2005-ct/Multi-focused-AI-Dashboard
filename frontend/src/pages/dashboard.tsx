import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { logoutUser, getToken } from '../api/authapi'
import SQLQueryOptimizer from '../components/SQLQueryOptimizer'
import DBConnectionForm from '../components/DBConnectionForm'
import SavedConnections from '../components/SavedConnections'

interface ActiveConnection {
  id: number
  host: string
  database: string
  username: string
  tables: string[]
}

function Dashboard() {
  const navigate = useNavigate()
  const [activeConnection, setActiveConnection] = useState<ActiveConnection | null>(null)

  const handleLogout = () => {
    logoutUser()
    navigate('/')
  }

  const handleConnectionSelect = (connection: ActiveConnection | null) => {
    setActiveConnection(connection)
  }

  return (
    <div style={styles.page}>
      {/* Navbar */}
      <nav style={styles.navbar}>
        <div style={styles.navContent}>
          <div style={styles.navBrand}>
            <div style={styles.navLogo}>AI</div>
            <span style={styles.navTitle}>AI Dashboard</span>
          </div>
          <div style={styles.navRight}>
            <span style={styles.navUser}>
              {getToken() ? 'Authenticated' : ''}
            </span>
            <button onClick={handleLogout} style={styles.logoutBtn}>
              Sign Out
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div style={styles.main}>
        <div style={styles.welcome}>
          <h1 style={styles.welcomeTitle}>Welcome to AI Dashboard</h1>
          <p style={styles.welcomeSub}>
            Optimize your SQL queries using natural language and manage your database connections.
          </p>
        </div>

        <div style={styles.layout}>
          {/* Row 1: SQL Optimizer + DB Connection side by side */}
          <div style={styles.row}>
            <div style={styles.halfColumn}>
              <SQLQueryOptimizer activeConnection={activeConnection} />
            </div>
            <div style={styles.halfColumn}>
              <DBConnectionForm />
            </div>
          </div>

          {/* Row 2: Saved Connections full width */}
          <div style={styles.fullWidth}>
            <SavedConnections onConnectionSelect={handleConnectionSelect} />
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer style={styles.footer}>
        <p style={{ margin: 0 }}> 2026 AI Dashboard. Powered by Flask & React</p>
      </footer>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: '#0f0c29',
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    display: 'flex',
    flexDirection: 'column' as const,
  },
  navbar: {
    background: 'rgba(26, 26, 46, 0.95)',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    padding: '0 24px',
    position: 'sticky' as const,
    top: 0,
    zIndex: 100,
    backdropFilter: 'blur(12px)',
  },
  navContent: {
    maxWidth: '1200px',
    margin: '0 auto',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: '64px',
  },
  navBrand: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  navLogo: {
    width: '36px',
    height: '36px',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #667eea, #764ba2)',
    color: '#fff',
    fontSize: '14px',
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  navTitle: {
    color: '#ffffff',
    fontSize: '18px',
    fontWeight: 600,
  },
  navRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  navUser: {
    color: '#8b8ba7',
    fontSize: '13px',
  },
  logoutBtn: {
    background: 'rgba(255,255,255,0.06)',
    border: '1px solid rgba(255,255,255,0.1)',
    color: '#b8b8d0',
    borderRadius: '8px',
    padding: '8px 16px',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  main: {
    flex: 1,
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '32px 24px',
    width: '100%',
  },
  welcome: {
    marginBottom: '32px',
  },
  welcomeTitle: {
    color: '#ffffff',
    fontSize: '28px',
    fontWeight: 700,
    margin: '0 0 8px 0',
  },
  welcomeSub: {
    color: '#8b8ba7',
    fontSize: '15px',
    margin: 0,
  },
  layout: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '24px',
  },
  row: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '24px',
  },
  halfColumn: {
    flex: '1 1 400px',
    minWidth: '0',
  },
  fullWidth: {
    width: '100%',
  },
  footer: {
    textAlign: 'center' as const,
    color: '#5a5a7a',
    fontSize: '13px',
    padding: '24px',
    borderTop: '1px solid rgba(255,255,255,0.04)',
    marginTop: 'auto',
  },
}

export default Dashboard