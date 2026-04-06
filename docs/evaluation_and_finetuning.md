# Evaluation and Fine-Tuning Playbook

Version: 1.0
Date: April 6, 2026

This playbook defines how to evaluate quality and how to execute phase-two adaptation safely.

## 1. Evaluation Goals

Before any fine-tuning, establish a baseline on:

- coding quality
- architecture reasoning
- response correctness
- latency and usability

## 2. Baseline Evaluation Setup

## 2.1 Build Evaluation Dataset

Create task sets from your real workflows:

- code explanation tasks
- bug triage tasks
- refactor proposal tasks
- documentation synthesis tasks

Each sample should include:

- prompt
- expected outcome criteria
- grading rubric

## 2.2 Compare Profiles

Evaluate at least:

- `E4B 8-bit`
- `E4B 16-bit`
- `26B A4B 4-bit`

Track:

- correctness score
- completion usefulness score
- average first-token latency
- total response latency

## 2.3 Acceptance Gate for Phase 2

Phase 2 starts only when:

- assistant is used in recurring workflows
- baseline quality and latency are documented
- evaluation harness is repeatable

## 3. Fine-Tuning Approach (Phase 2)

Recommended adaptation path:

- PEFT LoRA / QLoRA (not full retraining)

High-level workflow:

1. curate training/eval datasets
2. clean and deduplicate data
3. run LoRA adaptation on selected base profile
4. evaluate against frozen baseline
5. promote only if quality improves without harmful regressions

## 4. Safety and Governance

- Keep versioned model checkpoints
- Keep immutable baseline model for rollback
- Never deploy adapted model without evaluation report
- Maintain prompt + model version traceability in release notes

## 5. Release Decision Framework

Promote adapted model if all are true:

- quality delta positive on target tasks
- no major regression in general assistant behavior
- latency remains within acceptable range for intended mode
- rollback is tested

## 6. Suggested Repo Additions for Phase 2

Future directories:

- `finetune/data/`
- `finetune/train/`
- `finetune/eval/`
- `finetune/reports/`

Future automation:

- training workflow in CI (manual trigger)
- model artifact publishing with version tags
- regression benchmark gate before release