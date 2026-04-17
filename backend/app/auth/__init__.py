"""
Authentication and authorization (Phase 8).

Modules:
    models          - User DB model
    crypto          - Fernet encryption for secrets at rest
    github_oauth    - GitHub OAuth2 authorization flow
    token_service   - JWT session token issue / validate / refresh
    dependencies    - FastAPI dependency injectors (get_current_user, etc.)
"""
