# FUTURE.md — deferred until production justification exists

## Distributed multi-node orchestration
- Vector clock state locking
- P2P WebSocket heartbeats between orchestrator nodes  
- Merge conflict resolution across AGENTS.md replicas
**Trigger:** build this when 2+ orchestrator nodes exist in prod.

## Android/iOS on-device inference
- Gemma4 E2B/E4B embedded via MediaPipe or llama.cpp JNI
**Trigger:** build this when phone-side latency matters more than cost.

## Phase 15 — Potential Field Cursor Control (Deferred)
- **Spatial Model**: Mathematical potential fields mapping screen elements as attractive/repulsive coordinate forces.
- **Cursor Guidance**: Smooth, dynamic cursor trajectories and micro-interactivity adjustments inside active single-window coordinates.
**Trigger:** Implement when mouse gliding latency must match human muscle response limits.

## Phase 16 — 3D Window Depth Graph Navigation (Deferred)
- **3D Graph Model**: Represents desktop window stacks as a 3D coordinate space (X/Y screen space, Z window depth layers where Z=0 is foreground).
- **Occlusion Detection**: Identifies overlapping windows to determine blocked/unreachable coordinates before clicking.
- **Z-Navigation Primitives**:
  - *Bring forward*: Target window at Z=1+ called via focus-stealing, moving it to Z=0 and shifting other layers back.
  - *Push back*: Active window at Z=0 dismissed/resolved to let the underlying target rise to Z=0.
  - *Stay in place*: Keep focus and Z-coordinate constant while navigating X/Y plane for task actions.
**Trigger:** Implement when multi-app desktop automation requires proactive 3D spatial reasoning rather than blind, reactive clicking on flat 2D screenshots.
