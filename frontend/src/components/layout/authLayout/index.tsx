
import { Outlet } from 'react-router-dom'
import './index.scss'

import { Typography } from 'antd'

const { Title } = Typography

const AuthLayout = () => {
  return (
    <div className="auth-layout">
      <div className="auth-content">
        <Title level={2}>Multi-focused AI Dashboard</Title>
        <Outlet />
      </div>
    </div>
  )
}

export default AuthLayout
