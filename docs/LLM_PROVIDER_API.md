# LLM Provider Management API

> **Status**: Implemented (Phase 1 complete)  
> **Endpoints prefix**: `/admin/llm-providers`  
> **Auth**: Requires `superadmin` or `admin` role

---

## Overview

Eidos supports **dynamic LLM provider management**. Instead of relying solely on environment variables (`EIDOS_LLM_BASE_URL`, `EIDOS_LLM_API_KEY`, etc.), administrators can register, update, test, and switch between multiple LLM providers at runtime — no restart needed.

The system is compatible with **any OpenAI-compatible API**, including:
- **Fanar** (`https://api.fanar.qa/v1`)
- **OpenAI** (`https://api.openai.com/v1`)
- **Ollama** (`http://localhost:11434/v1`)
- **LM Studio** (`http://localhost:1234/v1`)
- **vLLM** / **llama.cpp** / **LocalAI**
- **Azure OpenAI**, **Together AI**, **Groq**, etc.

---

## Architecture

```
???????????????????????????????????????????????????????????
?  Admin API                                              ?
?  POST/GET/PATCH/DELETE /admin/llm-providers             ?
???????????????????????????????????????????????????????????
                  ?
                  ?
???????????????????????????????????????????????????????????
?  LLMProvider (DB model)                                 ?
?  - name, base_url, api_key_enc (AES encrypted)         ?
?  - default_model, is_active, is_default                 ?
?  - temperature, max_tokens, timeout, rate_limit_rpm     ?
???????????????????????????????????????????????????????????
                  ?
                  ?
???????????????????????????????????????????????????????????
?  get_llm_config_from_provider(db, provider_id, model)   ?
?  ? LLMConfig ? create_llm_client() ? OpenAICompatible  ?
???????????????????????????????????????????????????????????
                  ?
                  ?
???????????????????????????????????????????????????????????
?  Consumers:                                             ?
?  • /repos/{id}/snapshots/{id}/ask     (reasoning)       ?
?  • /repos/{id}/snapshots/{id}/review  (reviews)         ?
?  • /repos/{id}/snapshots/{id}/docs    (docgen)          ?
???????????????????????????????????????????????????????????
```

---

## API Endpoints

### Register a Provider

```http
POST /admin/llm-providers
Content-Type: application/json

{
  "name": "Fanar",
  "base_url": "https://api.fanar.qa/v1",
  "api_key": "your-api-key",
  "default_model": "Fanar-C-2-27B",
  "max_tokens": 4096,
  "temperature": 0.1,
  "timeout": 60,
  "rate_limit_rpm": 50,
  "is_active": true
}
```

**Response** (201):
```json
{
  "id": "a1b2c3d4e5f6",
  "name": "Fanar",
  "base_url": "https://api.fanar.qa/v1",
  "default_model": "Fanar-C-2-27B",
  "is_active": true,
  "is_default": false,
  "has_api_key": true,
  "max_tokens": 4096,
  "temperature": 0.1,
  "timeout": 60,
  "rate_limit_rpm": 50,
  "created_at": "2025-07-01T10:00:00+00:00",
  "updated_at": "2025-07-01T10:00:00+00:00"
}
```

### List Providers

```http
GET /admin/llm-providers
```

### Get Provider Details

```http
GET /admin/llm-providers/{provider_id}
```

### Update Provider

```http
PATCH /admin/llm-providers/{provider_id}
Content-Type: application/json

{
  "default_model": "Fanar-Sadiq",
  "api_key": "new-key"
}
```

### Delete Provider

```http
DELETE /admin/llm-providers/{provider_id}
```

### Set Default Provider

```http
POST /admin/llm-providers/{provider_id}/set-default
```

### Test Connectivity

```http
POST /admin/llm-providers/{provider_id}/test
```

**Response**:
```json
{
  "status": "ok",
  "models": ["Fanar-C-2-27B", "Fanar-Sadiq", "Fanar-Sadiq-Agentic"],
  "provider": "Fanar"
}
```

### Get LLM Status

```http
GET /admin/llm-providers/status
```

**Response**:
```json
{
  "configured": true,
  "default_provider": {
    "name": "Fanar",
    "base_url": "https://api.fanar.qa/v1",
    "default_model": "Fanar-C-2-27B"
  },
  "fallback_to_env": false,
  "total_providers": 2,
  "active_providers": 2
}
```

---

## Per-Request Provider/Model Selection

All LLM-consuming endpoints now accept optional query parameters:

| Parameter | Description |
|-----------|-------------|
| `provider_id` | Use a specific registered provider instead of the default |
| `model` | Override the provider's default model for this request |

### Examples

```http
# Use Fanar-Sadiq for this question
POST /repos/myrepo/snapshots/snap1/ask?model=Fanar-Sadiq
{"question": "What is the architecture?"}

# Use a specific provider
POST /repos/myrepo/snapshots/snap1/review?provider_id=prov-ollama
{"diff": "..."}

# Use a specific provider AND model
POST /repos/myrepo/snapshots/snap1/docs?provider_id=prov-fanar&model=Fanar-C-2-27B
```

---

## Config Resolution Order

1. **Query parameter** `provider_id` ? use that specific provider from DB
2. **Default provider** ? use the provider marked `is_default=True` in DB
3. **Environment variables** ? fall back to `EIDOS_LLM_BASE_URL` etc.
4. **No LLM** ? use `StubLLMClient` (deterministic responses)

---

## Security

- API keys are **AES-encrypted at rest** using Fernet (via `app/auth/crypto.py`)
- The `has_api_key` field is returned instead of the actual key
- Only `superadmin` and `admin` roles can manage providers
- API keys are decrypted only at LLM call time

---

## Database Model

```python
class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id: str              # 12-char hex ID
    name: str            # Display name ("Fanar", "OpenAI", "Ollama")
    base_url: str        # API base URL
    api_key_enc: str     # AES-encrypted API key
    default_model: str   # Default model name
    is_active: bool      # Can be used
    is_default: bool     # System default (only one at a time)
    max_tokens: int      # Default max tokens
    temperature: float   # Default temperature
    timeout: int         # Request timeout (seconds)
    rate_limit_rpm: int  # Rate limit (requests per minute)
    created_at: datetime
    updated_at: datetime
```

---

## Quick Setup: Fanar

```bash
# Register Fanar as a provider
curl -X POST http://localhost:8000/admin/llm-providers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Fanar",
    "base_url": "https://api.fanar.qa/v1",
    "api_key": "YOUR_FANAR_API_KEY",
    "default_model": "Fanar-C-2-27B",
    "rate_limit_rpm": 50
  }'

# Set it as default
curl -X POST http://localhost:8000/admin/llm-providers/{id}/set-default

# Test connectivity
curl -X POST http://localhost:8000/admin/llm-providers/{id}/test
```

---

## Testing

The provider system has **54 backend tests** covering:
- Full CRUD lifecycle
- Default provider switching
- Connectivity testing (mocked)
- Config resolution (DB ? env ? none)
- API key encryption round-trip
- Per-request provider/model override wiring
- Integration with reasoning, reviews, and docgen endpoints
- Edge cases (inactive providers, bad keys, duplicates)

Run tests:
```bash
cd backend
python -m pytest tests/test_llm_providers.py tests/test_llm_dynamic_integration.py -v
```
