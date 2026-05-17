import { Outlet } from 'react-router-dom'

const AppLayout = () => {
  return (
    <div className="app-layout">
      <div className="app-content">
        <Outlet />
      </div>
    </div>
  )
}

export default AppLayout
