# Model Selector Pipeline

Version: 1.0  
Date: April 6, 2026

Goal: provide a ChatGPT-style model selector in the UI that can switch between:

- `Gemma 4 E4B 16-bit`
- `Gemma 4 E4B 8-bit`
- `Gemma 4 26B A4B 4-bit`

## 1. Configuration Source of Truth

- File: `config/model_profiles.yaml`
- Purpose: register available models, limits, defaults, and fallback behavior.

At app startup, backend loads this file and exposes only enabled profiles to the UI.

## 2. Backend Contract

## 2.1 List selectable models

- `GET /v1/models`
- Returns lightweight metadata for selector menu.

Example response:

```json
{
  "default_model_id": "gemma4_e4b_8bit",
  "models": [
    {
      "id": "gemma4_e4b_16bit",
      "display_name": "Gemma 4 E4B 16-bit",
      "tier": "balanced_quality",
      "quantization": "bf16",
      "description": "Highest-fidelity E4B profile. Slower on 8GB VRAM due to offload."
    },
    {
      "id": "gemma4_e4b_8bit",
      "display_name": "Gemma 4 E4B 8-bit",
      "tier": "default",
      "quantization": "sfp8",
      "description": "Best daily balance of quality and speed on this laptop."
    },
    {
      "id": "gemma4_26b_a4b_4bit",
      "display_name": "Gemma 4 26B A4B 4-bit",
      "tier": "deep_quality",
      "quantization": "q4",
      "description": "Highest quality mode on this laptop, with slower responses."
    }
  ]
}
```

## 2.2 Set current default model

- `POST /v1/model-selection`
- Body: `{ "model_id": "gemma4_e4b_8bit" }`
- Effect: updates user/global default model for new chats.

## 2.3 Get current default model

- `GET /v1/model-selection`

## 2.4 Per-request override

- `POST /v1/chat/completions`
- Include `model` field to override default for one request.

Example:

```json
{
  "model": "gemma4_26b_a4b_4bit",
  "messages": [
    { "role": "user", "content": "Review this architecture for reliability risks." }
  ],
  "stream": true
}
```

## 3. UI Behavior

## 3.1 Selector placement

- Model dropdown in top bar and in new-chat panel.

## 3.2 Selection policy

- New chats use current default model.
- Each chat stores its own selected model.
- User can change model mid-chat; next turn uses the new model.

## 3.3 UX states

- `Ready`: model loaded.
- `Warming`: lazy load in progress.
- `Fallback`: backend switched model due to OOM/timeout.
- `Unavailable`: model asset missing.

## 4. Runtime Switching Strategy

- Use lazy loading to avoid loading all models at once.
- Keep one hot model in memory (default `E4B 8-bit`).
- Unload inactive models after TTL (`unload_inactive_after_minutes`).
- On OOM, fallback to configured model and notify UI in response metadata.

## 5. Recommended Defaults for Your Laptop

- Default: `gemma4_e4b_8bit`
- Heavy task mode: `gemma4_26b_a4b_4bit`
- Fidelity test mode: `gemma4_e4b_16bit`

## 6. Acceptance Criteria for This Feature

- Selector lists all configured models dynamically from backend.
- Changing selector changes subsequent responses.
- Chat retains selected model after app restart.
- OOM/timeout fallback returns explicit metadata (`used_model`, `fallback_reason`).
- No UI crash if selected model is not currently loaded.