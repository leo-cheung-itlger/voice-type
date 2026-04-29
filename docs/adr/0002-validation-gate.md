# ADR-0002: Require validation gates for implementation tasks

## Status

Accepted

## Context

The project can compile while still failing at runtime or in the visible UI. VoiceType also depends on local processes, browser behavior, microphone input, model files, and OS-level keyboard/clipboard interaction, so build-only validation is insufficient.

## Decision

Every substantial implementation task must define acceptance criteria and a validation gate before execution. After changes, the implementer must run the gate or record the exact blocker. Frontend work requires a browser/runtime smoke check in addition to typecheck/build. Service work requires endpoint or protocol smoke checks. Daily ASR work requires a real input-to-output smoke test when local hardware and models are available.

## Consequences

- Completion reports distinguish implemented, verified, and blocked states.
- Runtime/UI errors should be caught before handoff.
- When independent verifier agents are available and authorized, they should be used for high-risk changes; otherwise the implementer performs a second self-check.
