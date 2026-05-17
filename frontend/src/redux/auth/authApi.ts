import API from '../../apiInstance'
import { AUTH_LOGIN, AUTH_REGISTER } from '../../utils/apiEndPoints'
import type { AxiosResponse } from 'axios'

export interface AuthCredentials {
  email: string
  password: string
}

export interface SignupCredentials extends AuthCredentials {
  name: string
}

export interface AuthSuccessResponse {
  token: string
  user: {
    id: number
    email: string
    name: string
    [key: string]: string | number | boolean | null | undefined
  }
}

export const loginRequest = (payload: AuthCredentials) => {
  return API.post<AuthSuccessResponse>(AUTH_LOGIN, payload)
}

export const registerRequest = (payload: SignupCredentials) => {
  return API.post<AuthSuccessResponse>(AUTH_REGISTER, payload)
}

export type LoginResponse = AxiosResponse<AuthSuccessResponse>
export type RegisterResponse = AxiosResponse<AuthSuccessResponse>
