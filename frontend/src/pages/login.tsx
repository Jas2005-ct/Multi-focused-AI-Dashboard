

import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { loginUser, googleLoginUser } from '../api/authapi'
import { GoogleLogin } from '@react-oauth/google'
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

  const handleGoogleSuccess = async (response: any) => {
    try {
      const res = await googleLoginUser(response.credential)
      saveToken(res.data.token)
      navigate('/dashboard')
    } catch {
      alert("Google Login Failed")
    }
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

      <GoogleLogin
        onSuccess={handleGoogleSuccess}
        onError={() => alert("Google Auth Failed")}
      />

      <p>Don't have account? <Link to="/register">Register</Link></p>
    </div>
  )
}

export default Login