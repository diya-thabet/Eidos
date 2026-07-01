"""
Admin API for managing LLM providers.

Allows dynamic registration, update, deletion and testing of LLM providers
(Fanar, OpenAI, Ollama, etc.) without backend restart.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crypto import decrypt, encrypt
from app.auth.dependencies import get_current_user, require_role
from app.core.config import settings
from app.reasoning.llm_client import LLMConfig
from app.storage.database import get_db
from app.storage.models import LLMProvider, User

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class LLMProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    default_model: str = ""
    max_tokens: int = 2048
    temperature: float = 0.1
    timeout: int = 60
    rate_limit_rpm: int = 50
    is_active: bool = True


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    timeout: int | None = None
    rate_limit_rpm: int | None = None
    is_active: bool | None = None


def _provider_to_dict(p: LLMProvider) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "default_model": p.default_model,
        "is_active": p.is_active,
        "is_default": p.is_default,
        "max_tokens": p.max_tokens,
        "temperature": p.temperature,
        "timeout": p.timeout,
        "rate_limit_rpm": p.rate_limit_rpm,
        "has_api_key": bool(p.api_key_enc),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/llm-providers",
    status_code=201,
    summary="Register a new LLM provider",
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def create_provider(
    body: LLMProviderCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Any:
    """Register a new LLM provider (e.g. Fanar, OpenAI, Ollama)."""
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="Provider name is required")
    if not body.base_url or not body.base_url.strip():
        raise HTTPException(status_code=400, detail="Base URL is required")

    provider_id = uuid.uuid4().hex[:12]
    api_key_enc = encrypt(body.api_key) if body.api_key else ""

    provider = LLMProvider(
        id=provider_id,
        name=body.name.strip(),
        base_url=body.base_url.strip().rstrip("/"),
        api_key_enc=api_key_enc,
        default_model=body.default_model.strip() if body.default_model else "",
        is_active=body.is_active,
        is_default=False,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        timeout=body.timeout,
        rate_limit_rpm=body.rate_limit_rpm,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _provider_to_dict(provider)


@router.get(
    "/llm-providers",
    summary="List all LLM providers",
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Any:
    """List all configured LLM providers."""
    result = await db.execute(select(LLMProvider).order_by(LLMProvider.name))
    providers = result.scalars().all()
    return [_provider_to_dict(p) for p in providers]


@router.get(
    "/llm-providers/status",
    summary="Get current LLM configuration status",
)
async def llm_status(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Any:
    """Return the current LLM configuration status."""
    result = await db.execute(
        select(LLMProvider).where(LLMProvider.is_default.is_(True))
    )
    default = result.scalar_one_or_none()

    # Count active providers
    active_result = await db.execute(
        select(LLMProvider).where(LLMProvider.is_active.is_(True))
    )
    active_count = len(active_result.scalars().all())

    if default:
        return {
            "configured": True,
            "default_provider": _provider_to_dict(default),
            "active_providers": active_count,
            "fallback_to_env": False,
        }

    # Fallback to env-based config
    if settings.llm_base_url:
        return {
            "configured": True,
            "default_provider": {
                "name": "Environment Config",
                "base_url": settings.llm_base_url,
                "default_model": settings.llm_model,
                "is_default": True,
            },
            "active_providers": active_count,
            "fallback_to_env": True,
        }

    return {
        "configured": False,
        "default_provider": None,
        "active_providers": active_count,
        "fallback_to_env": False,
    }


@router.get(
    "/llm-providers/{provider_id}",
    summary="Get LLM provider details",
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Any:
    """Get details for a specific LLM provider."""
    provider = await db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _provider_to_dict(provider)


@router.patch(
    "/llm-providers/{provider_id}",
    summary="Update an LLM provider",
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def update_provider(
    provider_id: str,
    body: LLMProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Any:
    """Update an LLM provider's configuration."""
    provider = await db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if body.name is not None:
        provider.name = body.name.strip()
    if body.base_url is not None:
        provider.base_url = body.base_url.strip().rstrip("/")
    if body.api_key is not None:
        provider.api_key_enc = encrypt(body.api_key) if body.api_key else ""
    if body.default_model is not None:
        provider.default_model = body.default_model.strip()
    if body.max_tokens is not None:
        provider.max_tokens = body.max_tokens
    if body.temperature is not None:
        provider.temperature = body.temperature
    if body.timeout is not None:
        provider.timeout = body.timeout
    if body.rate_limit_rpm is not None:
        provider.rate_limit_rpm = body.rate_limit_rpm
    if body.is_active is not None:
        provider.is_active = body.is_active

    await db.commit()
    await db.refresh(provider)
    return _provider_to_dict(provider)


@router.delete(
    "/llm-providers/{provider_id}",
    status_code=204,
    summary="Delete an LLM provider",
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    """Delete an LLM provider."""
    provider = await db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(provider)
    await db.commit()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@router.post(
    "/llm-providers/{provider_id}/set-default",
    summary="Set a provider as the default",
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def set_default_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Any:
    """Set an LLM provider as the system default."""
    provider = await db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider.is_active:
        raise HTTPException(status_code=400, detail="Cannot set inactive provider as default")

    # Clear existing default
    await db.execute(
        update(LLMProvider).where(LLMProvider.is_default.is_(True)).values(is_default=False)
    )
    provider.is_default = True
    await db.commit()
    await db.refresh(provider)
    return _provider_to_dict(provider)


@router.post(
    "/llm-providers/{provider_id}/test",
    summary="Test connectivity to an LLM provider",
    dependencies=[Depends(require_role("superadmin", "admin"))],
)
async def test_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Any:
    """Test connectivity by calling the provider's /models endpoint."""
    provider = await db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = ""
    if provider.api_key_enc:
        try:
            api_key = decrypt(provider.api_key_enc)
        except ValueError:
            return {"status": "error", "detail": "Failed to decrypt API key"}

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"{provider.base_url}/models"
    try:
        async with httpx.AsyncClient(timeout=provider.timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            models = []
            if "data" in data:
                models = [m.get("id", m.get("name", "")) for m in data["data"]]
            return {
                "status": "ok",
                "models": models,
                "provider": provider.name,
            }
    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "detail": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200]}


# ---------------------------------------------------------------------------
# Helper: get LLM config from DB provider
# ---------------------------------------------------------------------------


async def get_llm_config_from_provider(
    db: AsyncSession,
    provider_id: str | None = None,
    model_override: str | None = None,
) -> LLMConfig | None:
    """
    Build an LLMConfig from a stored provider.

    If provider_id is None, uses the default provider.
    Falls back to env-based settings if no DB provider found.
    """
    if provider_id:
        provider = await db.get(LLMProvider, provider_id)
    else:
        result = await db.execute(
            select(LLMProvider).where(
                LLMProvider.is_default.is_(True),
                LLMProvider.is_active.is_(True),
            )
        )
        provider = result.scalar_one_or_none()

    if provider:
        api_key = ""
        if provider.api_key_enc:
            try:
                api_key = decrypt(provider.api_key_enc)
            except ValueError:
                pass
        return LLMConfig(
            base_url=provider.base_url,
            api_key=api_key,
            model=model_override or provider.default_model,
            temperature=provider.temperature,
            max_tokens=provider.max_tokens,
            timeout=provider.timeout,
        )

    # Fallback to env
    if settings.llm_base_url:
        return LLMConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=model_override or settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )

    return None
