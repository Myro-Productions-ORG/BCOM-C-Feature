# ADR-006: Bob Voice Assistant Architecture

**Status:** Accepted  
**Date:** 2026-02-28  
**Authors:** Myro Productions

---

## Context

BCOM-C is the operator dashboard for the Bob-AI Pipeline. We want to add a multimodal voice assistant ("Bob") that integrates into the dashboard as a web feature, supporting voice over phone (Twilio), local mic, and webcam vision.

## Decision

- **Fork BCOM-C** into `BCOM-C-Feature` to develop Bob in isolation from the webhook-synced parent repo.
- **Cascading architecture** (STT + LLM + TTS pipeline) rather than a single end-to-end speech model, for modularity and GPU flexibility.
- **Anthropic Claude** as the dialog/brain LLM, with ElevenLabs for TTS and FasterWhisper/Silero for STT+VAD.
- **Twilio ConversationRelay** for phone-mode audio, providing low-latency full-duplex WebSocket audio.
- **GPU inference distributed** across DGX Spark (70B orchestrator), Linux desktop 4070 (STT/smaller models), and M4 Pro (development + deployment).
- **Phased rollout:** local prototype first, telephony second, vision+tools third, hardening fourth.

## Consequences

- Bob development does not trigger BCOM-C webhooks or CI/CD on the parent repo's synced nodes.
- The cascading pipeline introduces per-stage latency (VAD + STT + LLM + TTS) but allows independent scaling and debugging of each component.
- ElevenLabs dependency means TTS quality is high but introduces an external API cost and network hop.
- Twilio adds telephony capability but requires account setup, phone numbers, and ConversationRelay configuration.
- Integration back into BCOM-C dashboard will happen via clean API boundaries once Bob is stable.

## Alternatives Considered

- **Build inside BCOM-C directly** — Rejected due to webhook auto-sync risk and scope mismatch.
- **End-to-end speech model (e.g., GPT-4o Realtime)** — Rejected for now; cascading gives more control over each stage and leverages existing GPU infra.
- **Self-hosted TTS (Coqui/VITS)** — May revisit later for cost savings, but ElevenLabs quality is preferred for v1.
