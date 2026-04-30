

import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { loginUser } from '../api/authapi'
import { saveToken } from '../api/authapi'

function Login() {
  const navigate = useNavigate()

  const [form, setForm] = useState({
    email: '',
    password: ''
  })

  const [loading, setLoading] = useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  const handleLogin = async () => {
    try {
      setLoading(true)
      const res = await loginUser(form)

      saveToken(res.data.token)
      navigate('/dashboard')

    } catch (error: any) {
      alert(error?.response?.data?.error || "Login Failed")
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleRedirect = () => {
    window.location.href = `${import.meta.env.VITE_API_URL}/auth/login`
  }

  return (
    <div className="auth-container">
      <h2>Login</h2>

      <input name="email" placeholder="Email" onChange={handleChange} />
      <input name="password" type="password" placeholder="Password" onChange={handleChange} />
      <h1>hi</h1>
      <button onClick={handleLogin}>
        {loading ? "Please wait..." : "Login"}
      </button>

      <br /><br />

      <button onClick={handleGoogleRedirect}>Login with Google</button>

      <p>Don't have account? <Link to="/register">Register</Link></p>
    </div>
  )
}

export default Login