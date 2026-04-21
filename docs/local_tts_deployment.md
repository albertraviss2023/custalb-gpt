# Local TTS Deployment (No External API)

This project supports fully local TTS playback for CBI panel speech.

## Provider Options
- `kokoro` (default): lower latency for interactive panel simulation.
- `xtts`: higher realism at higher compute cost.

## Runtime Settings
Configure backend environment variables:

```env
GOI_TTS_PROVIDER=kokoro
GOI_TTS_KOKORO_BASE_URL=http://goi-kokoro-tts:8880
GOI_TTS_KOKORO_SYNTHESIZE_PATH=/v1/synthesize
GOI_TTS_XTTS_BASE_URL=http://goi-xtts-tts:8020
GOI_TTS_XTTS_SYNTHESIZE_PATH=/api/tts
GOI_TTS_TIMEOUT_SECONDS=30
```

## Docker Compose Profiles
Start stack with Kokoro profile:

```bash
docker compose -f infra/docker-compose.yml --profile tts-kokoro up -d
```

Start stack with XTTS profile:

```bash
docker compose -f infra/docker-compose.yml --profile tts-xtts up -d
```

Start both providers:

```bash
docker compose -f infra/docker-compose.yml --profile tts-all up -d
```

## Notes
- Frontend panel audio now calls backend `/v1/tts/speak`.
- Browser `speechSynthesis` is not used for panel playback.
- If local TTS is unavailable, panel audio shows an actionable error and interview continues.
