import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { Button, Form, Input, Typography, Alert } from 'antd'
import type { RootState } from '../../../redux/store'
import { loginRequest } from '../../../redux/auth/authSlice'

const { Text } = Typography

const Login = () => {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { loading, error, token } = useSelector((state: RootState) => state.auth)

  useEffect(() => {
    if (token) {
      navigate('/app')
    }
  }, [token, navigate])

  const onFinish = (values: { email: string; password: string }) => {
    dispatch(loginRequest(values))
  }

  return (
    <div className="auth-page">
      <Form
        name="login"
        layout="vertical"
        className='form-login'
        requiredMark={false}
        onFinish={onFinish}
        style={{ width: 320 }}
      >
        {error ? (
          <Form.Item>
            <Alert message={error} type="error" showIcon />
          </Form.Item>
        ) : null}

        <Form.Item
          label="Email"
          name="email"
          rules={[
            { required: true, message: 'Please enter your email' },
            { type: 'email', message: 'Enter a valid email address' },
          ]}
        >
          <Input placeholder="Email" />
        </Form.Item>

        <Form.Item
          label="Password"
          name="password"
          rules={[{ required: true, message: 'Please enter your password' }]}
        >
          <Input.Password placeholder="Password" />
        </Form.Item>

        <Form.Item>
          <Button type="primary" className="btn-login" htmlType="submit" block loading={loading}>
            Login
          </Button>
        </Form.Item>

        <Text className="redirect-text">
          Don't have an account? 
          <Link to="/signup" className="redirect-link">
            Sign up
          </Link>
        </Text>
      </Form>
    </div>
  )
}

export default Login;
