# Local Authentication — Implementation Guide

## Overview

Eidos now supports **three authentication methods**:

1. **GitHub OAuth** — Sign in with GitHub account
2. **Google OAuth** — Sign in with Google account
3. **Local (email + password)** — Traditional signup/login without external providers

All three methods issue the same JWT token format and work with the existing RBAC system.

---

## Architecture

```
???????????????????????????????????????????????????????????
?  Frontend (login page)                                   ?
?                                                          ?
?  ????????????  ????????????  ???????????????????????   ?
?  ?  GitHub   ?  ?  Google   ?  ?  Email + Password   ?   ?
?  ?  OAuth    ?  ?  OAuth    ?  ?  (local auth)       ?   ?
?  ????????????  ????????????  ???????????????????????   ?
???????????????????????????????????????????????????????????
        ?               ?                  ?
        ?               ?                  ?
?????????????????????????????????????????????????????????????
?  Backend API                                               ?
?                                                            ?
?  GET /auth/login       ? GitHub redirect                   ?
?  GET /auth/callback    ? GitHub token exchange             ?
?  GET /auth/google/login ? Google redirect                  ?
?  GET /auth/google/callback ? Google token exchange         ?
?  POST /auth/signup     ? Create local user                 ?
?  POST /auth/login      ? Authenticate local user           ?
?  GET /auth/me          ? Current user info                 ?
?                                                            ?
?  All return: { access_token, token_type, user }            ?
?????????????????????????????????????????????????????????????
                           ?
                           ?
????????????????????????????????????????????????????????????
?  JWT Token (24h expiry)                                   ?
?  Payload: { sub: user_id, iat, exp }                      ?
?  Signed with: EIDOS_SECRET_KEY (HS256)                    ?
????????????????????????????????????????????????????????????
```

---

## API Endpoints

### POST /auth/signup

Create a new user with email and password.

**Request:**
```json
{
    "email": "user@example.com",
    "password": "securePass123",
    "name": "John Doe"
}
```

**Response (200):**
```json
{
    "access_token": "eyJ...",
    "token_type": "bearer",
    "user": {
        "id": "lo-abc123...",
        "login": "local:user@example.com",
        "name": "John Doe",
        "email": "user@example.com",
        "role": "user",
        "avatar_url": ""
    }
}
```

**Errors:**
- `409` — Email already registered
- `422` — Password too short (min 6 chars) or missing fields

---

### POST /auth/login

Authenticate with email and password.

**Request:**
```json
{
    "email": "user@example.com",
    "password": "securePass123"
}
```

**Response (200):** Same format as signup.

**Errors:**
- `401` — Invalid email or password

---

### GET /auth/me

Returns the currently authenticated user.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**
```json
{
    "id": "lo-abc123...",
    "github_login": "local:user@example.com",
    "auth_provider": "local",
    "name": "John Doe",
    "email": "user@example.com",
    "avatar_url": "",
    "role": "user"
}
```

---

## Database Configuration

### In-Memory SQLite (Development/Demo)

Set in `.env` or environment variables:

```env
EIDOS_IN_MEMORY_DB=true
EIDOS_AUTH_ENABLED=true
EIDOS_SECRET_KEY=my-dev-secret-key-32-chars-long!
```

This creates `eidos_demo.db` in the working directory. No PostgreSQL needed.

### PostgreSQL (Production)

```env
EIDOS_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/eidos
EIDOS_AUTH_ENABLED=true
EIDOS_SECRET_KEY=<random-32-char-production-secret>
```

### Demo Mode (No Auth)

```env
EIDOS_AUTH_ENABLED=false
```

When auth is disabled, all requests get anonymous superadmin access. The frontend skips the login page.

---

## Password Security

Passwords are hashed using **bcrypt** (12 rounds) when available.

If `bcrypt` is not installed, the system falls back to **PBKDF2-SHA256** (100,000 iterations).

Stored format:
- bcrypt: `$2b$12$...` (standard bcrypt hash)
- PBKDF2 fallback: `pbkdf2:<base64-salt>:<base64-hash>`

Both are verified transparently.

### Install bcrypt (recommended):
```bash
pip install bcrypt
```

---

## User Model

Local users are stored in the same `users` table as OAuth users:

| Field | Value for Local Users |
|---|---|
| `id` | `lo-<uuid16>` |
| `auth_provider` | `"local"` |
| `github_login` | `"local:<email>"` (used as unique key) |
| `email` | User's email |
| `password_hash` | bcrypt or PBKDF2 hash |
| `role` | `"user"` (default) |

---

## Running Tests

```bash
cd backend
python -m pytest tests/test_local_auth.py -v
```

**Requirements:**
- `pytest`
- `pytest-asyncio`
- `httpx`
- `aiosqlite`

All tests use **in-memory SQLite** — no external database needed.

### Test Coverage

| Test | What It Verifies |
|---|---|
| `test_signup_success` | Creates user, returns token + user info |
| `test_signup_duplicate_email` | Rejects duplicate registration (409) |
| `test_signup_short_password` | Rejects passwords < 6 chars (422) |
| `test_signup_missing_fields` | Rejects empty email/password (422) |
| `test_login_success` | Authenticates after signup, returns token |
| `test_login_wrong_password` | Rejects wrong password (401) |
| `test_login_nonexistent_user` | Rejects unknown email (401) |
| `test_me_with_token` | /me returns user info with valid token |
| `test_me_without_token` | /me returns 401 without token |
| `test_case_insensitive_email` | Email matching ignores case |
| `test_password_hash_and_verify` | Direct password module unit test |
| `test_empty_hash` | Empty/null hash returns False |

---

## Frontend Integration

The login page (`pgLogin`) provides:

1. **Sign In / Sign Up tabs** — Toggle between login and registration
2. **Email + Password form** — Client-side validation (min 6 chars)
3. **GitHub OAuth button** — Redirects to GitHub
4. **Google OAuth button** — Redirects to Google
5. **Demo Mode** — Skip auth entirely

### Flow:

1. App starts ? `Auth.detectAuthMode()` calls `GET /auth/me`
2. If 401 ? auth is enabled, show login page
3. If anonymous user returned ? demo mode, skip login
4. User fills form ? `POST /auth/signup` or `POST /auth/login`
5. On success ? token stored in `localStorage`, user cached, navigate to repos
6. All subsequent API calls include `Authorization: Bearer <token>`
7. If token expires ? periodic check redirects to login with toast

---

## Configuration Summary

| Variable | Default | Description |
|---|---|---|
| `EIDOS_AUTH_ENABLED` | `false` | Enable authentication enforcement |
| `EIDOS_SECRET_KEY` | `change-me...` | JWT signing key (HS256) |
| `EIDOS_JWT_EXPIRE_SECONDS` | `86400` | Token lifetime (24h) |
| `EIDOS_IN_MEMORY_DB` | `false` | Use SQLite instead of PostgreSQL |
| `EIDOS_DATABASE_URL` | `postgresql+asyncpg://...` | Database connection string |
| `EIDOS_GITHUB_CLIENT_ID` | `""` | GitHub OAuth app ID |
| `EIDOS_GITHUB_CLIENT_SECRET` | `""` | GitHub OAuth app secret |
| `EIDOS_GOOGLE_CLIENT_ID` | `""` | Google OAuth client ID |
| `EIDOS_GOOGLE_CLIENT_SECRET` | `""` | Google OAuth client secret |

---

## Quick Start (Local Dev)

```bash
# 1. Set environment
export EIDOS_IN_MEMORY_DB=true
export EIDOS_AUTH_ENABLED=true
export EIDOS_SECRET_KEY="dev-secret-key-change-in-prod!!"

# 2. Start backend
cd backend
uvicorn app.main:app --reload

# 3. Open frontend
# Navigate to frontend-lite/index.html
# You'll see the login page with Sign In / Sign Up tabs
```

---

## Security Notes

1. **Passwords are never stored in plaintext** — always hashed with bcrypt or PBKDF2
2. **JWT tokens expire after 24h** — configurable via `EIDOS_JWT_EXPIRE_SECONDS`
3. **Email uniqueness** — enforced at database level via unique constraint on `github_login`
4. **Case-insensitive email** — `Alice@Example.COM` and `alice@example.com` are the same user
5. **Frontend advisory only** — all permission checks are enforced on the backend; frontend UI hiding is cosmetic
6. **Change the secret key in production** — `EIDOS_SECRET_KEY` must be unique and random
