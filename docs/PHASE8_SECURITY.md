# Phase 8 -- Security & Multi-tenant Basics

## Overview

Phase 8 adds authentication, authorization, data isolation, and
safe secret storage. The system supports **GitHub OAuth** and
**Google OAuth** login, JWT sessions, encrypted token storage,
per-user repo ownership, and automatic clone cleanup after indexing.

**Key principle:** Auth is opt-in via `EIDOS_AUTH_ENABLED=true`.
When disabled (default), all endpoints work without tokens for
local development and testing.

## Authentication Flow

```
  Browser                  Eidos API                 GitHub
     |                        |                        |
     |-- GET /auth/login ---->|                        |
     |<-- 302 redirect ------+-- authorize URL ------->|
     |                        |                        |
     |-- (user authorizes) ---|------- callback ------>|
     |                        |<-- code + state -------|
     |                        |                        |
     |                        |-- POST token exchange ->|
     |                        |<-- access_token --------|
     |                        |                        |
     |                        |-- GET /user ----------->|
     |                        |<-- profile -------------|
     |                        |                        |
     |<-- JWT + user info ----+                        |
     |                        |                        |
     |-- Bearer JWT --------->| (all subsequent calls) |
```

The same flow applies to **Google OAuth** via `/auth/google/login`
and `/auth/google/callback`, except the external provider is
`accounts.google.com` instead of `github.com`.

## Components

### 1. Crypto (`auth/crypto.py`)

- Fernet symmetric encryption (AES-128-CBC)
- Key derived from `EIDOS_SECRET_KEY` via SHA-256
- Used to encrypt GitHub tokens before DB storage
- `encrypt(plaintext) -> ciphertext`
- `decrypt(ciphertext) -> plaintext`

### 2. Token Service (`auth/token_service.py`)

- JWT (HS256) session tokens
- `create_access_token(user_id, expires_in, extra)`
- `decode_access_token(token)` -- validates signature + expiry
- Default TTL: 24 hours (`EIDOS_JWT_EXPIRE_SECONDS`)

### 3. GitHub OAuth (`auth/github_oauth.py`)

- `build_authorize_url(state)` -- constructs GitHub auth URL
- `exchange_code(code)` -- trades callback code for access token
- `fetch_github_user(token)` -- gets profile from GitHub API
- Scopes: `read:user user:email`

### 3b. Google OAuth (`auth/google_oauth.py`)

- `build_google_authorize_url(state)` -- constructs Google auth URL
- `exchange_google_code(code)` -- trades callback code for access token
- `fetch_google_user(token)` -- gets profile from Google API
- Scopes: `openid email profile`
- Rejects unverified email addresses
- Users identified by `google:<email>` in the `github_login` column

### 4. Dependencies (`auth/dependencies.py`)

FastAPI dependency injectors:

- **`get_current_user`** -- validates Bearer JWT, returns User row.
  When `auth_enabled=False`, returns a synthetic "anonymous" user.
- **`get_optional_user`** -- same but returns None instead of 401.
- **`require_repo_access`** -- verifies `repo.owner_id == user.id`.
  Returns 404 (not 403) to avoid leaking repo existence.

### 5. Auth API (`api/auth.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/login` | GET | Redirect to GitHub OAuth |
| `/auth/callback` | GET | Handle GitHub OAuth callback, issue JWT |
| `/auth/google/login` | GET | Redirect to Google OAuth |
| `/auth/google/callback` | GET | Handle Google OAuth callback, issue JWT |
| `/auth/me` | GET | Get current user info |
| `/auth/logout` | POST | Client-side token discard hint |

### 6. Data Retention (`core/retention.py`)

- `cleanup_clone(repo_id, snapshot_id)` -- delete clone dir after indexing
- `cleanup_all_repo_clones(repo_id)` -- delete all clones for a repo
- Controlled by `EIDOS_DELETE_CLONES_AFTER_INDEXING` (default: true)
- Integrated into the ingestion task pipeline

## Database Changes

### New Table: `users`

```sql
CREATE TABLE users (
    id              VARCHAR(48) PRIMARY KEY,
    auth_provider   VARCHAR(16) DEFAULT 'github',  -- github | google
    github_id       INTEGER UNIQUE,
    github_login    VARCHAR(256) UNIQUE NOT NULL,   -- or 'google:<email>'
    name            VARCHAR(512) DEFAULT '',
    email           VARCHAR(512) DEFAULT '',
    avatar_url      TEXT DEFAULT '',
    github_token_enc TEXT DEFAULT '',  -- Fernet-encrypted
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### Modified Table: `repos`

```sql
ALTER TABLE repos ADD COLUMN owner_id VARCHAR(48)
    REFERENCES users(id) ON DELETE SET NULL;
```

When auth is disabled, `owner_id` is NULL. When enabled, it's
set to the authenticated user on repo creation.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EIDOS_AUTH_ENABLED` | `false` | Enable auth enforcement |
| `EIDOS_SECRET_KEY` | (dev default) | Key for JWT + Fernet |
| `EIDOS_JWT_EXPIRE_SECONDS` | `86400` | Token TTL (24h) |
| `EIDOS_GITHUB_CLIENT_ID` | `""` | GitHub OAuth app ID |
| `EIDOS_GITHUB_CLIENT_SECRET` | `""` | GitHub OAuth secret |
| `EIDOS_GITHUB_REDIRECT_URI` | `http://localhost:8000/auth/callback` | OAuth callback URL |
| `EIDOS_GOOGLE_CLIENT_ID` | `""` | Google OAuth app ID |
| `EIDOS_GOOGLE_CLIENT_SECRET` | `""` | Google OAuth secret |
| `EIDOS_GOOGLE_REDIRECT_URI` | `http://localhost:8000/auth/google/callback` | Google callback URL |
| `EIDOS_DELETE_CLONES_AFTER_INDEXING` | `true` | Auto-delete clones |

## Security Properties

1. **Isolation** -- users can only access repos where `owner_id` matches
2. **No existence leaks** -- unauthorized repo access returns 404, not 403
3. **Secrets at rest** -- GitHub/Google tokens are Fernet-encrypted in DB
4. **Short-lived sessions** -- JWT expires after 24h
5. **No code execution** -- no eval/exec paths in the codebase
6. **Clone cleanup** -- temporary repo data deleted after indexing
7. **Backward compatible** -- auth is off by default, no breaking changes
8. **Multi-provider** -- supports GitHub and Google OAuth independently

## Test Coverage

| File | Tests | Scope |
|------|-------|-------|
| `test_crypto.py` | 6 | Encrypt/decrypt round-trip, invalid data, empty/long strings |
| `test_token_service.py` | 10 | JWT create/decode, expiry, tampering, extra claims |
| `test_github_oauth.py` | 5 | Authorize URL, code exchange, user fetch (all mocked) |
| `test_google_oauth.py` | 7 | Google authorize URL, code exchange, user fetch, unverified email |
| `test_auth_api.py` | 9 | GitHub login redirect, callback, me, logout, user upsert |
| `test_google_auth_api.py` | 7 | Google login/callback, user create/update, unverified rejection |
| `test_auth_dependencies.py` | 7 | Anonymous mode, JWT validation, repo isolation |
| `test_retention.py` | 5 | Clone cleanup, disabled mode, missing dirs |
| `test_security_scenarios.py` | 7 | Cross-user isolation, ownership on create, anonymous mode |
| `test_integration_e2e.py` | 36 | Full pipeline: symbols, edges, overview, docs, eval, lifecycle |
| `test_cross_module.py` | 37 | Analysis?indexing, embedder, guardrails, diff, question router |
| `test_edge_cases.py` | 37 | Empty snapshots, invalid inputs, graph, sanitizer, data integrity |
| `test_schemas_comprehensive.py` | 39 | All Pydantic schemas, DB models, dataclasses |
