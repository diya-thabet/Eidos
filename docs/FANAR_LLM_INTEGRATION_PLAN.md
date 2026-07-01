# Fanar LLM Integration — Implementation Plan

> **Goal**: Integrate the Fanar LLM API (https://api.fanar.qa) into the Eidos backend and frontend, enable dynamic switching between LLM providers and models, and allow runtime API key configuration — so the RAG pipeline, Q&A, documentation generation and code review features work with Fanar out of the box.

---

## 1. Current State

### What We Have

| Component | File | Description |
|---|---|---|
| LLM Client Abstraction | `app/reasoning/llm_client.py` | `LLMClient` ABC, `OpenAICompatibleClient`, `StubLLMClient`, `create_llm_client()` factory |
| LLM Config Dataclass | `app/reasoning/llm_client.py` | `LLMConfig(base_url, api_key, model, temperature, max_tokens, timeout)` |
| Settings | `app/core/config.py` | `llm_base_url`, `llm_api_key`, `llm_model`, `llm_temperature`, `llm_max_tokens`, `llm_timeout` |
| Config Helper | `app/api/reasoning.py` | `_get_llm_config()` builds `LLMConfig` from `settings` |
| Usage Points | `app/api/reasoning.py`, `app/docgen/`, `app/indexing/` | Q&A, doc generation, summarization |
| Stub Client | `app/reasoning/llm_client.py` | Returns deterministic responses when no LLM is configured |

### How It Works Today

1. A single LLM provider is configured via `.env` (`EIDOS_LLM_BASE_URL`, `EIDOS_LLM_API_KEY`, `EIDOS_LLM_MODEL`).
2. The `create_llm_client()` factory checks if `base_url` is set and creates either an `OpenAICompatibleClient` or a `StubLLMClient`.
3. The client calls `POST {base_url}/chat/completions` with an OpenAI-compatible payload.
4. Configuration is static — changing provider requires restarting the backend.

### What's Missing

- No multi-provider registry.
- No runtime API key or model switching.
- No admin API to manage LLM configurations.
- No frontend UI for provider/model selection.
- No Fanar-specific model metadata.

---

## 2. Fanar API Compatibility Analysis

### Fanar API Overview

| Property | Value |
|---|---|
| Base URL | `https://api.fanar.qa` |
| Auth | `Authorization: Bearer YOUR_API_KEY` |
| Chat endpoint | `POST /v1/chat/completions` |
| Models endpoint | `GET /v1/models` |
| Tokens endpoint | `POST /v1/tokens` |
| Rate limits | 50 req/min for chat models |

### Compatibility with OpenAI Format

Fanar uses the **OpenAI-compatible** format:

- Same `POST /v1/chat/completions` endpoint.
- Same `Authorization: Bearer` header.
- Same request/response JSON structure.

**Conclusion**: Our existing `OpenAICompatibleClient` already works with Fanar. No new client class is needed — only configuration and dynamic switching.

### Available Fanar Models

| Model ID | Type | Rate Limit |
|---|---|---|
| `Fanar` | General Arabic LLM | 50 req/min |
| `Fanar-S-1-7B` | Small general | 50 req/min |
| `Fanar-C-1-8.7B` | Code-oriented | 50 req/min |
| `Fanar-C-2-27B` | Code-oriented (large) | 50 req/min |
| `Fanar-Sadiq` | Advanced reasoning | 50 req/min |
| `Fanar-Sadiq-Agentic` | Agentic (tool-calling) | 50 req/min |
| `Fanar-Guard-2` | Content moderation | 50 req/min |
| `Fanar-Diwan` | Poetry/literature | 50 req/min |

**Best models for Eidos code intelligence**:
- `Fanar-C-2-27B` — code understanding, documentation, reviews.
- `Fanar-Sadiq` — reasoning, Q&A, architecture questions.
- `Fanar-Sadiq-Agentic` — agentic workflows, tool-calling.

---

## 3. Implementation Plan

### Phase 1: Multi-Provider LLM Registry (Backend) — ? COMPLETE

> **Status**: Fully implemented and tested (54 backend tests passing).  
> **Files**: `app/storage/models.py`, `app/api/llm_providers.py`, `app/api/reasoning.py`, `app/api/reviews.py`, `app/api/docgen.py`, `app/main.py`  
> **Tests**: `tests/test_llm_providers.py` (31 tests), `tests/test_llm_dynamic_integration.py` (23 tests)  
> **Docs**: See `docs/LLM_PROVIDER_API.md` for full API reference.

#### 3.1.1 New Database Model: `LLMProvider`

Create a new model to store configured LLM providers.

```python
# app/storage/models.py

class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)  # "Fanar", "OpenAI", "Ollama"
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_enc: Mapped[str] = mapped_column(Text, default="")  # AES-encrypted
    default_model: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    temperature: Mapped[float] = mapped_column(Float, default=0.1)
    timeout: Mapped[int] = mapped_column(Integer, default=60)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=...)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=...)
```

#### 3.1.2 Admin API: `/admin/llm-providers`

| Method | Path | Description |
|---|---|---|
| POST | `/admin/llm-providers` | Register a new LLM provider |
| GET | `/admin/llm-providers` | List all configured providers |
| GET | `/admin/llm-providers/{id}` | Get provider details |
| PATCH | `/admin/llm-providers/{id}` | Update provider (key, model, etc.) |
| DELETE | `/admin/llm-providers/{id}` | Remove a provider |
| POST | `/admin/llm-providers/{id}/test` | Test connectivity (call `/v1/models`) |
| POST | `/admin/llm-providers/{id}/set-default` | Set as the default provider |

#### 3.1.3 Updated `create_llm_client()` Factory

```python
async def create_llm_client_dynamic(
    db: AsyncSession,
    provider_id: str | None = None,
    model_override: str | None = None,
) -> LLMClient:
    """
    Create an LLM client using either a specific provider or the default.
    Falls back to settings-based config, then to StubLLMClient.
    """
    ...
```

#### 3.1.4 Fanar Seeding

On startup or via admin API, seed the Fanar provider:

```python
{
    "name": "Fanar",
    "base_url": "https://api.fanar.qa/v1",
    "api_key": "<user-provided>",
    "default_model": "Fanar-C-2-27B",
    "rate_limit_rpm": 50
}
```

---

### Phase 2: Dynamic Model Selection API — ? COMPLETE

> **Status**: Fully implemented and tested (19 additional tests).  
> **New endpoints**: `GET /admin/llm-providers/models` (aggregate), `GET /admin/llm-providers/{id}/models`, `POST /admin/llm-providers/chat` (playground)  
> **Tests**: `tests/test_llm_phase2.py` (19 tests)

#### 3.2.1 Per-Request Model Override ?

All LLM-consuming endpoints accept `?provider_id=` and `?model=` query params.

#### 3.2.2 Model Listing Endpoint ?

- `GET /admin/llm-providers/models` — aggregates models from all active providers in parallel
- `GET /admin/llm-providers/{id}/models` — lists models for a specific provider

#### 3.2.3 Provider Status Endpoint ?

`GET /admin/llm-providers/status` — returns default provider, active count, env fallback status.

#### 3.2.4 Direct Chat Endpoint ? (bonus)

`POST /admin/llm-providers/chat` — playground/testing endpoint for direct LLM interaction.

---

### Phase 3: Runtime API Key Management — ? COMPLETE

> **Status**: Fully implemented and tested.  
> **Feature**: Auto-validation on key update via `?validate_key=true` query param.

#### 3.3.1 Encrypted Key Storage ?

API keys are AES-encrypted at rest using Fernet (`app/auth/crypto.py`).

#### 3.3.2 Key Update Without Restart ?

`PATCH /admin/llm-providers/{id}` with `{"api_key": "new-key"}` — encrypts and saves immediately.

#### 3.3.3 Key Validation ?

`PATCH /admin/llm-providers/{id}?validate_key=true` — tests the key against `/v1/models` before saving. Returns 400 if validation fails.

---

### Phase 4: Frontend LLM Settings UI — ? COMPLETE

> **Status**: Fully implemented.  
> **Files**: `frontend-lite/js/llm-admin.js`, `frontend-lite/js/pages.js`, `frontend-lite/css/llm.css`, `frontend-lite/index.html`

#### 3.4.1 Admin Settings Page ?

- "LLM" tab in Admin Panel with:
  - LLM status overview (connected/disconnected, default provider, model, active count)
  - Provider list with status dots, default badge, key indicator
  - Add provider form (name, URL, API key, model, tokens, temperature, timeout, RPM)
  - Test connectivity button per provider
  - List models button per provider
  - Set default / delete buttons
  - Chat playground with provider/model selection

#### 3.4.2 Model Selector in Analysis Pages ?

- Provider/model dropdown in **Ask** (Q&A) page
- Provider/model dropdown in **PR Review** page
- Provider/model dropdown in **Documentation** generation page
- All pass `?provider_id=` and `?model=` query params to the backend

#### 3.4.3 Status Indicator ?

- LLM Status card in admin panel shows:
  - Green dot = connected (default provider active)
  - Warning = fallback to env vars
  - Gray = no provider configured

---

### Phase 5: RAG Pipeline Enhancement for Fanar — ~3h

#### 3.5.1 Prompt Optimization for Fanar Models

Fanar models are Arabic-first but support English. Optimize system prompts:

- Use clear structured instructions.
- Test prompt effectiveness with Fanar-C-2-27B for code tasks.
- Test Fanar-Sadiq for reasoning/architecture questions.
- Add model-specific prompt templates if needed.

#### 3.5.2 Token Counting

Use Fanar's `/v1/tokens` endpoint to count tokens before sending requests, enabling:

- Context window management.
- Cost estimation.
- Automatic context truncation when approaching limits.

#### 3.5.3 Rate Limit Awareness

Implement a per-provider rate limiter:

- Track requests per minute per provider.
- Return 429 with retry-after if rate limit would be exceeded.
- Queue requests when near the limit.

#### 3.5.4 Moderation Integration

Use `Fanar-Guard-2` via `/v1/moderations` to check:

- User questions before sending to the main model.
- Generated answers before returning to the user.
- This enhances the existing guardrails system.

---

### Phase 6: Testing and Validation — ~2h

#### 3.6.1 Unit Tests

- Test `create_llm_client_dynamic()` with mocked DB.
- Test admin CRUD endpoints for providers.
- Test key encryption/decryption round-trip.
- Test model override in Q&A endpoint.
- Test rate limiter logic.

#### 3.6.2 Integration Tests

- Test full Q&A flow with mocked Fanar responses.
- Test doc generation with Fanar model selection.
- Test provider failover (if default is down, try next).
- Test key rotation without restart.

#### 3.6.3 Manual Validation

- Register Fanar with real API key.
- Ask code questions ? verify Fanar-Sadiq answers.
- Generate docs ? verify Fanar-C-2-27B output.
- Switch between Fanar and OpenAI ? verify both work.

---

## 4. Configuration Examples

### Fanar Configuration (`.env`)

```env
# Primary LLM: Fanar
EIDOS_LLM_BASE_URL=https://api.fanar.qa/v1
EIDOS_LLM_API_KEY=your-fanar-api-key-here
EIDOS_LLM_MODEL=Fanar-C-2-27B
EIDOS_LLM_TEMPERATURE=0.1
EIDOS_LLM_MAX_TOKENS=2048
EIDOS_LLM_TIMEOUT=60
```

### Multi-Provider via Admin API

```bash
# Add Fanar
curl -X POST http://localhost:8000/admin/llm-providers \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "Fanar",
    "base_url": "https://api.fanar.qa/v1",
    "api_key": "your-fanar-key",
    "default_model": "Fanar-C-2-27B",
    "rate_limit_rpm": 50
  }'

# Add OpenAI as fallback
curl -X POST http://localhost:8000/admin/llm-providers \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "OpenAI",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "default_model": "gpt-4o-mini",
    "rate_limit_rpm": 500
  }'

# Set Fanar as default
curl -X POST http://localhost:8000/admin/llm-providers/{fanar_id}/set-default \
  -H "Authorization: Bearer $TOKEN"
```

### Per-Request Model Selection

```bash
# Use Fanar-Sadiq for reasoning questions
curl -X POST http://localhost:8000/repos/{id}/snapshots/{sid}/ask \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "question": "How does the authentication flow work?",
    "model": "Fanar-Sadiq"
  }'

# Use Fanar-C-2-27B for code-focused questions
curl -X POST http://localhost:8000/repos/{id}/snapshots/{sid}/ask \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "question": "What does this function do?",
    "target_symbol": "OrderService.process_payment",
    "model": "Fanar-C-2-27B"
  }'
```

---

## 5. Architecture After Implementation

```text
???????????????????????????????????????????????????
?                  Frontend                         ?
?  ????????????  ????????????  ????????????????  ?
?  ? Q&A Panel?  ? Doc Gen  ?  ? LLM Settings ?  ?
?  ? [model?] ?  ? [model?] ?  ? (Admin)      ?  ?
?  ????????????  ????????????  ????????????????  ?
???????????????????????????????????????????????????
        ?              ?               ?
        ?              ?               ?
???????????????????????????????????????????????????
?              Backend API                          ?
?                                                   ?
?  /ask?model=X    /docs?model=X   /admin/llm-*   ?
?       ?               ?               ?          ?
?       ?               ?               ?          ?
?  ????????????????????????????????????????????   ?
?  ?       Dynamic LLM Client Factory          ?   ?
?  ?  create_llm_client_dynamic(provider, model)?   ?
?  ????????????????????????????????????????????   ?
?             ?               ?                    ?
?     ?????????????   ???????????????            ?
?     ?  Provider  ?   ?  Provider   ?            ?
?     ?  Registry  ?   ?  Registry   ?            ?
?     ?  (DB)      ?   ?  (fallback) ?            ?
?     ?????????????   ???????????????            ?
???????????????????????????????????????????????????
              ?              ?
     ???????????????  ??????????????
     ?  Fanar API  ?  ? OpenAI API ?
     ?  api.fanar  ?  ? or Ollama  ?
     ?  .qa/v1     ?  ? or vLLM    ?
     ???????????????  ??????????????
```

---

## 6. Execution Timeline

| Phase | Task | Effort | Priority |
|---|---|---|---|
| 1 | Multi-Provider Registry (DB model + Admin API) | 4h | P0 |
| 2 | Dynamic Model Selection (per-request override) | 3h | P0 |
| 3 | Runtime API Key Management | 2h | P0 |
| 4 | Frontend LLM Settings UI | 4h | P1 |
| 5 | RAG Pipeline Enhancement (prompts, tokens, rate limits) | 3h | P1 |
| 6 | Testing and Validation | 2h | P0 |
| **Total** | | **~18h** | |

---

## 7. Quick Start (Immediate — No Code Changes)

Before implementing the full multi-provider system, Fanar works **today** with zero code changes:

```env
# backend/.env
EIDOS_LLM_BASE_URL=https://api.fanar.qa/v1
EIDOS_LLM_API_KEY=your-fanar-api-key
EIDOS_LLM_MODEL=Fanar-C-2-27B
```

Restart the backend and the existing `OpenAICompatibleClient` will route all LLM calls to Fanar. This is because Fanar uses the OpenAI-compatible chat completions format.

---

## 8. Model Recommendation for Eidos Tasks

| Eidos Feature | Recommended Fanar Model | Why |
|---|---|---|
| Q&A (architecture questions) | `Fanar-Sadiq` | Best reasoning capabilities |
| Q&A (code-specific questions) | `Fanar-C-2-27B` | Code-trained, large context |
| Documentation generation | `Fanar-C-2-27B` | Code understanding + generation |
| PR Review enrichment | `Fanar-C-1-8.7B` | Fast, code-aware, sufficient for review |
| Summarization | `Fanar-S-1-7B` | Fast, cheap, good for bulk summaries |
| Content moderation | `Fanar-Guard-2` | Built for safety checks |
| Agentic workflows (future) | `Fanar-Sadiq-Agentic` | Tool-calling support |

---

## 9. Success Criteria

- [ ] Fanar works as the default LLM provider with zero code changes (env only).
- [ ] Admin can register multiple providers via API.
- [ ] Admin can switch default provider without restart.
- [ ] Admin can update API keys without restart.
- [ ] Users can select model per request in Q&A/docs.
- [ ] Frontend shows provider status and model selector.
- [ ] Rate limits are respected per provider.
- [ ] Tests cover provider CRUD, key rotation and model switching.
- [ ] Full RAG pipeline (retrieve ? enrich ? answer) works with Fanar models.
