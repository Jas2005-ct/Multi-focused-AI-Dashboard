/**
 * Password policy — must stay in sync with the backend.
 *
 * Backend: backend/auths/schemas.py -> RegisterRequest.validate_password_strength
 *   - at least 8 characters
 *   - at least one uppercase letter
 *   - at least one lowercase letter
 *   - at least one digit
 *
 * The client used to only check for 6 characters, so a password that looked
 * valid in the UI was rejected by the API with an opaque 422.
 */
export const PASSWORD_MIN_LENGTH = 8

export const PASSWORD_RULES: readonly string[] = [
  `At least ${PASSWORD_MIN_LENGTH} characters`,
  'One uppercase letter (A–Z)',
  'One lowercase letter (a–z)',
  'One digit (0–9)',
]

export const PASSWORD_REQUIREMENTS_TEXT = PASSWORD_RULES.join(', ')

export interface PasswordCheck {
  valid: boolean
  /** First unmet requirement, or undefined when the password is fine. */
  message?: string
}

/** Validate a password against the backend policy. */
export function validatePassword(password: string): PasswordCheck {
  if (!password) {
    return { valid: false, message: 'Password is required' }
  }
  if (password.length < PASSWORD_MIN_LENGTH) {
    return { valid: false, message: `Password must be at least ${PASSWORD_MIN_LENGTH} characters` }
  }
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one uppercase letter' }
  }
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one lowercase letter' }
  }
  if (!/\d/.test(password)) {
    return { valid: false, message: 'Password must contain at least one digit' }
  }
  return { valid: true }
}
