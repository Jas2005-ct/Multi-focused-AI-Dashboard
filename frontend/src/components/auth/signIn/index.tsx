import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDispatch, useSelector } from 'react-redux'
import { Button, Form, Input, Typography, Alert } from 'antd'
import type { RootState } from '../../../redux/store'
import { registerRequest } from '../../../redux/auth/authSlice'

const { Text } = Typography

const Signup = () => {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { loading, error, token } = useSelector((state: RootState) => state.auth)

  useEffect(() => {
    if (token) {
      navigate('/app')
    }
  }, [token, navigate])

  const onFinish = (values: { name: string; email: string; password: string }) => {
    dispatch(registerRequest(values))
  }

  return (
    <div className="auth-page">
      <Form
        name="signup"
        layout="vertical"
        className='form-signup'
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
          label="Full Name"
          name="name"
          rules={[{ required: true, message: 'Please enter your full name' }]}
        >
          <Input placeholder="Full Name" />
        </Form.Item>

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
          <Button type="primary" className="btn-signup" htmlType="submit" block loading={loading}>
            Sign Up
          </Button>
        </Form.Item>

        <Text className="redirect-text">
          Already have an account? 
          <Link to="/login" className="redirect-link">
            Login
          </Link>
        </Text>
      </Form>
    </div>
  )
}

export default Signup;
