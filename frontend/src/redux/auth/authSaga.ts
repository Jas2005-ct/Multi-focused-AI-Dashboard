import { call, put, takeLatest } from 'redux-saga/effects'
import type { PayloadAction } from '@reduxjs/toolkit'
import type { AxiosError } from 'axios'
import {
  loginRequest as loginApi,
  registerRequest as registerApi,
  type AuthCredentials,
  type SignupCredentials,
  type LoginResponse,
  type RegisterResponse,
} from './authApi'
import {
  loginFailure,
  loginSuccess,
  registerFailure,
  registerSuccess,
} from './authSlice'

type AuthError =
  | AxiosError<{ message?: string }>
  | Error
  | { response?: { data?: { message?: string } }; message?: string }

const getErrorMessage = (error: AuthError, fallback: string): string => {
  if ('response' in error && error.response?.data?.message) {
    return error.response.data.message
  }

  if ('message' in error && typeof error.message === 'string') {
    return error.message
  }

  return fallback
}

function* handleLogin(action: PayloadAction<AuthCredentials>) {
  try {
    const response: LoginResponse = yield call(loginApi, action.payload)
    const { token, user } = response.data
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify(user))
    yield put(loginSuccess({ token, user }))
  } catch (error) {
    const message = getErrorMessage(error as AuthError, 'Login failed')
    yield put(loginFailure(message))
  }
}

function* handleRegister(action: PayloadAction<SignupCredentials>) {
  try {
    const response: RegisterResponse = yield call(registerApi, action.payload)
    const { token, user } = response.data
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify(user))
    yield put(registerSuccess({ token, user }))
  } catch (error) {
    const message = getErrorMessage(error as AuthError, 'Registration failed')
    yield put(registerFailure(message))
  }
}

export default function* authSaga() {
  yield takeLatest('auth/loginRequest', handleLogin)
  yield takeLatest('auth/registerRequest', handleRegister)
}
