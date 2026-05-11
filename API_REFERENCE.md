# AI Dashboard - Backend API Reference

**Base URL:** `http://localhost:5000` (or your configured backend URL)

**CORS:** Configured for `http://localhost:5173` and `http://127.0.0.1:5173`

---

## Authentication

Most API endpoints require authentication via JWT token in the `Authorization` header:

```
Authorization: Bearer <jwt_token>
```

The token is obtained from:
- Login endpoints (email/password or Google OAuth)
- Stored in localStorage as `token` after login

---

## Auth Endpoints (`/auth`)

### 1. Email Login

**POST** `/auth/login`

Authenticate with email and password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "Password123"
}
```

**Response (200):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

**Error Responses:**
- `400` - Validation error (invalid email format)
- `401` - Invalid credentials

---

### 2. Register

**POST** `/auth/register`

Create a new account with email and password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "Password123",
  "name": "John Doe"
}
```

**Password Requirements:**
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit

**Response (201):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

**Error Responses:**
- `400` - Validation error
- `409` - Email already exists

---

### 3. Google OAuth Login

**GET** `/auth/login`

Redirects to Google OAuth login page. After successful authentication, redirects to:

```
/dashboard?token=<jwt_token>&user=<encoded_user_json>
```

The `user` parameter contains URL-encoded JSON:
```json
{"id": 1, "email": "user@example.com", "name": "John Doe"}
```

**Note:** The frontend should extract both `token` and `user` from the URL query parameters and store them in localStorage.

---

### 4. Google OAuth Callback

**GET** `/auth/callback`

Internal endpoint for Google OAuth callback. Do not call directly.

---

## SQL Query Endpoints (`/api`)

All endpoints below require JWT authentication.

### 5. Generate SQL Query

**POST** `/api/sql-query/`

Generate an optimized SQL query from natural language input.

**Request Body:**
```json
{
  "sentence": "Find all users who signed up in the last 30 days",
  "db_id": 1  // Optional - for schema context
}
```

**Field Validation:**
- `sentence` - Required, max 5000 characters, cannot be empty
- `db_id` - Optional, ID of saved database connection

**Response (200):**
```json
{
  "success": true,
  "output_query": "SELECT * FROM users WHERE created_at >= NOW() - INTERVAL '30 days'",
  "metadata": {
    "tables": ["users"],
    "columns": ["id", "email", "created_at"]
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Invalid or harmful query detected",
  "error_type": "security_error",
  "output_query": null
}
```

**Error Types:**
- `api_error` - LLM service error (500)
- `security_error` - Potentially harmful query blocked (400)
- `general` - Other validation errors (400)

---

### 6. Save Database Connection

**POST** `/api/db-connection`

Store database connection details securely (passwords are encrypted).

**Request Body (Individual Fields):**
```json
{
  "host": "localhost",
  "port": 5432,
  "database": "mydb",
  "username": "dbuser",
  "password": "dbpassword",
  "db_type": "postgresql"  // or "mysql"
}
```

**Request Body (Connection String):**
```json
{
  "connection_string": "postgresql://dbuser:dbpassword@localhost:5432/mydb",
  "db_type": "postgresql"
}
```

**Field Validation:**
- `port` - Must be between 1-65535
- `db_type` - Must be: `postgresql`, `postgres`, or `mysql`

**Response (200):**
```json
{
  "success": true,
  "message": "Database connection saved successfully"
}
```

**Error Responses:**
- `400` - Missing required fields or validation error
- `401` - Unauthorized
- `409` - Connection already exists
- `500` - Database error

---

### 7. Test Database Connection

**POST** `/api/test-connection/`

Test if a saved database connection is valid.

**Request Body:**
```json
{
  "db_id": 1
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Connection successful",
  "connection": {
    "id": 1,
    "host": "localhost",
    "port": 5432,
    "database": "mydb",
    "username": "dbuser",
    "created_at": "2024-01-15T10:30:00"
  },
  "tables": ["users", "orders", "products"]
}
```

**Response (500) - Connection Failed:**
```json
{
  "success": false,
  "message": "Failed to connect: connection refused"
}
```

---

### 8. Get Database Connections

**GET** `/api/get-connections/`

Retrieve all saved database connections for the authenticated user.

**Query Parameters:**
- `db_id` (optional) - Get specific connection details including tables

**Response (200) - All Connections:**
```json
{
  "success": true,
  "message": "Connections retrieved successfully",
  "connections": [
    {
      "id": 1,
      "host": "localhost",
      "port": 5432,
      "database": "mydb",
      "username": "dbuser",
      "created_at": "2024-01-15T10:30:00"
    }
  ]
}
```

**Response (200) - Single Connection (with db_id):**
```json
{
  "success": true,
  "message": "Connection successful",
  "connection": {
    "id": 1,
    "host": "localhost",
    "port": 5432,
    "database": "mydb",
    "username": "dbuser",
    "created_at": "2024-01-15T10:30:00"
  },
  "tables": ["users", "orders", "products"]
}
```

---

### 9. Delete Database Connection

**DELETE** `/api/delete-connection`

Delete a saved database connection.

**Request Body:**
```json
{
  "db_id": 1
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Connection deleted successfully"
}
```

**Error Responses:**
- `404` - Connection not found
- `401` - Unauthorized (not owner)
- `500` - Database error

---

## Data Models

### User
```typescript
interface User {
  id: number;
  email: string;
  name: string;
}
```

### DBConnection
```typescript
interface DBConnection {
  id: number;
  host: string;
  port: number;
  database: string;
  username: string;
  db_type: 'postgresql' | 'mysql';
  created_at: string; // ISO 8601 format
}
```

### AuthSuccess
```typescript
interface AuthSuccess {
  token: string;
  user: User;
}
```

### QueryResponse
```typescript
interface QueryResponse {
  success: boolean;
  output_query: string | null;
  metadata?: {
    tables?: string[];
    columns?: string[];
  };
  error?: string;
  error_type?: 'api_error' | 'security_error' | 'general';
}
```

---

## Error Response Format

All errors follow this structure:

```json
{
  "error": "Error Title",
  "message": "Detailed error description"
}
```

---

## Frontend Implementation Notes

### Token Storage
Store the JWT token and user data in localStorage after login:

```typescript
// After login
localStorage.setItem('token', response.data.token);
localStorage.setItem('user', JSON.stringify(response.data.user));

// Helper functions
export const getToken = () => localStorage.getItem('token');
export const getUser = () => {
  const userStr = localStorage.getItem('user');
  return userStr ? JSON.parse(userStr) : null;
};
export const logout = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
};
```

### Axios Configuration

```typescript
import axios from 'axios';

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL
});

// Add auth token to requests
API.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### Handling Google OAuth Redirect

After Google OAuth redirects back to `/dashboard`, extract the token and user:

```typescript
import { useSearchParams } from 'react-router-dom';

function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  
  useEffect(() => {
    const token = searchParams.get('token');
    const userParam = searchParams.get('user');
    
    if (token) {
      localStorage.setItem('token', token);
      
      if (userParam) {
        try {
          const user = JSON.parse(decodeURIComponent(userParam));
          localStorage.setItem('user', JSON.stringify(user));
        } catch {
          // ignore invalid user data
        }
      }
      
      // Clean up URL
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);
}
```

---

## Environment Variables

Frontend `.env` file:

```
VITE_API_URL=http://localhost:5000
```

---

## Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created (registration) |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized (invalid/missing token) |
| 404 | Not Found |
| 409 | Conflict (duplicate resource) |
| 500 | Internal Server Error |
