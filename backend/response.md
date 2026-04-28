# Backend API Response Documentation

## Overview

This document describes the backend API responses implemented in `backend/ai_dashboard/routes.py`.

The API is mounted under `/api` and is protected by Google OAuth session-based authentication. Any request to a protected endpoint without an active session redirects to `/auth/login`.

## Authentication

The backend uses Google OAuth via `/auth/login` and `/auth/callback`.

- `GET /auth/login`
  - Redirects the user to the Google sign-in page.

- `GET /auth/callback`
  - Handles Google OAuth callback.
  - Creates a user record if needed.
  - Saves `user_id` and `email` into session.
  - Redirects to `/api/` on success.

> Protected API endpoints require a valid session with `user_id` in Flask session.

## API Endpoints

### 1. GET `/api/`

Returns a simple health/status response.

- Response:
  - `200 OK`
  - Body: `"Hello, World!"`

### 2. POST `/api/sql-query/`

Generates an optimized SQL query from a natural language sentence.

- Request body:
```json
{
  "sentence": "Generate a query to find all active users created in the last 30 days"
}
```

- Response model:
  - `output_query` (string): Optimized SQL query.

- Example response:
```json
{
  "output_query": "SELECT * FROM users WHERE active = true AND created_at >= NOW() - INTERVAL '30 days';"
}
```

### 3. POST `/api/db-connection/`

Stores database connection details for the authenticated user.

- Request body:
```json
{
  "host": "localhost",
  "port": 5432,
  "database": "my_database",
  "username": "db_user",
  "password": "password123",
  "connection_string": "postgresql://db_user:password123@localhost:5432/my_database"
}
```

- Response bodies:
  - On success:
```json
{
  "message": "Database connection details stored successfully"
}
```
  - When an identical connection already exists:
```json
{
  "message": "Connection string already exists"
}
```

### 4. GET `/api/test/`

Simple authenticated test endpoint.

- Response:
  - `200 OK`
  - Body: `"Test successful!"`

## Request and Response Models

### `PromptRequest`

Used by `/api/sql-query/`.

- `input` (string): Natural language sentence to optimize.

### `QueryResponse`

Returned by `/api/sql-query/`.

- `output_query` (string): Optimized SQL query.

### `DBConnectionRequest`

Used by `/api/db-connection/`.

- `host` (string)
- `port` (integer)
- `database` (string)
- `username` (string)
- `password` (string)
- `connection_string` (string, optional)

## Notes

- The backend uses `flask-openapi3` with `OpenAPI` and `APIBlueprint`, but the current code does not expose a full OpenAPI JSON/YAML document unless configured explicitly.
- The `/api/sql-query/` endpoint internally converts the request to `PromptRequest` and returns `QueryResponse`.
- The `/api/db-connection/` endpoint stores connection details in the `DBConnection` model associated with the authenticated user.
