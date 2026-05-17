import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'

export interface User {
  id: number
  email: string
  name: string
  [key: string]: string | number | boolean | null | undefined
}

export interface AuthState {
  token: string | null
  user: User | null
  loading: boolean
  error: string | null
}

const initialState: AuthState = {
  token: localStorage.getItem('token'),
  user: localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')!) : null,
  loading: false,
  error: null,
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginRequest(state, _action: PayloadAction<{ email: string; password: string }>) {
      state.loading = true
      state.error = null
    },
    loginSuccess(state, action: PayloadAction<{ token: string; user: User }>) {
      state.loading = false
      state.token = action.payload.token
      state.user = action.payload.user
      state.error = null
    },
    loginFailure(state, action: PayloadAction<string>) {
      state.loading = false
      state.error = action.payload
    },
    registerRequest(state, _action: PayloadAction<{ name: string; email: string; password: string }>) {
      state.loading = true
      state.error = null
    },
    registerSuccess(state, action: PayloadAction<{ token: string; user: User }>) {
      state.loading = false
      state.token = action.payload.token
      state.user = action.payload.user
      state.error = null
    },
    registerFailure(state, action: PayloadAction<string>) {
      state.loading = false
      state.error = action.payload
    },
    logout(state) {
      state.token = null
      state.user = null
      state.loading = false
      state.error = null
    },
  },
})

export const {
  loginRequest,
  loginSuccess,
  loginFailure,
  registerRequest,
  registerSuccess,
  registerFailure,
  logout,
} = authSlice.actions

export default authSlice.reducer
