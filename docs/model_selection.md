# Model Selection for Zenbiok Pro Duo (32 GB RAM, RTX 3070 Ti 8 GB)

Version: 1.2  
Date: April 6, 2026

## 1. Decision Summary

Updated conclusion:

- `26B A4B` is feasible on this laptop in hybrid mode (RAM + GPU offload).
- Best daily balance of quality, speed, and reliability is `E4B 8-bit`.
- Keep `E4B 16-bit` as fidelity mode and `26B A4B 4-bit` as high-quality slow mode.

## 2. Gemma 4 Options

- `E2B`
- `E4B`
- `26B A4B` (MoE)
- `31B` (dense)

Official architecture facts:

- E2B and E4B: 128K context window
- 26B A4B and 31B: 256K context window
- E2B and E4B optimized for on-device efficiency

## 3. Memory Planning (Important)

Approximate model-weight memory estimates (from Gemma 4 guidance) show:

| Model | BF16 | SFP8 | Q4_0 |
|---|---|---|---|
| Gemma 4 E2B | 9.6 GB | 4.6 GB | 3.2 GB |
| Gemma 4 E4B | 15 GB | 7.5 GB | 5 GB |
| Gemma 4 26B A4B | 48 GB | 25 GB | 15.6 GB |
| Gemma 4 31B | 58.3 GB | 30.4 GB | 17.4 GB |

Interpretation for your hardware:

- `26B A4B` can run with combined RAM + VRAM, especially at lower-bit quantization.
- These numbers are for static weights only; runtime overhead and KV cache add extra memory pressure.
- Real throughput on 26B will usually be much slower than E4B on an 8 GB GPU.

## 4. Why Ollama Size Numbers May Differ

You may also see different model sizes in Ollama tags (for example 18 GB for `gemma4:26b`).
That does not always equal the full runtime memory footprint because packaging, quantization method, and runtime allocation strategy differ from simplified planning tables.

## 5. Capability vs Practicality on This Laptop

| Option | Capability | Practical Fit | Recommended Use |
|---|---|---|---|
| E2B | Good | Excellent | Optional fast profile (not in current MVP selector) |
| E4B | Better | Good | Default daily assistant (8-bit profile) |
| 26B A4B | High | Feasible but heavy | Deep tasks, slower mode |
| 31B | Highest | Borderline/poor | Not advised for daily local use |

## 6. Recommended 3-Mode Strategy (Implemented in MVP)

- `Balanced` (default): E4B 8-bit
- `Fidelity`: E4B 16-bit
- `Deep` (experimental): 26B A4B 4-bit

Operational defaults for `Deep` mode:

- Start with smaller context (for example 4K-16K)
- Expect slower token generation
- Fall back to E4B if latency is too high for interactive work

## 7. Final Recommendation

- Build Phase 1 around `E4B 8-bit` + `E4B 16-bit` + `26B A4B 4-bit`.
- Include optional E2B later if you want an additional low-latency profile.
- Keep Phase 2 fine-tuning gated until Phase 1 proves daily value.

## 8. Sources (Reviewed April 6, 2026)

- Gemma releases: https://ai.google.dev/gemma/docs/releases
- Gemma 4 model card: https://ai.google.dev/gemma/docs/core/model_card_4
- Gemma 4 launch blog: https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/
- Ollama Gemma 4 tags: https://ollama.com/library/gemma4/tags
