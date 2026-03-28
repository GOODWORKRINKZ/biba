# Build-Time Spectral Cache Design

## Goal

Remove multi-second runtime FFT preprocessing for production voice events by precomputing spectral playback frames during Docker image build, and add precise controller-side timing instrumentation to measure BMS-to-radio telemetry latency.

## Current State

The controller currently calls `wav_to_peak_frames()` on demand from `MotorSynth.play_spectral()`. On the Pi Zero 2W this preprocessing takes multiple seconds for real production WAV assets, which adds avoidable latency to arm, disarm, and connection voice events even after playback was moved off the main control path.

The repository already has an offline voice-preparation pipeline for generating approved WAV assets, but it stops at WAV output. There is no derived spectral cache artifact, no build-time generation step, and no runtime lookup path for precomputed frames.

The BMS telemetry path has already been shortened by caching slow BLE details, but current controller logs are too coarse to isolate the remaining delay between fresh BMS current and visible telemetry on the radio.

## Constraints

- Deployment must continue through the existing GitHub image build and robot-side `bbupdate` workflow.
- Derived spectral artifacts should not be committed into the repository.
- Runtime behavior must remain backward-compatible for temporary WAV files, audition assets, and unexpected paths.
- Spectral cache invalidation must be explicit when the analysis algorithm changes.
- The first pass should cover production voice WAV assets only.
- BMS latency measurement must use precise controller-side timestamps rather than the existing 5-second battery summary log.

## Options Considered

### Option A: Build-time cache files in a dedicated image directory

Generate spectral frame artifacts during Docker build into a dedicated cache directory such as `/app/voice-cache/`, then have runtime load them by lookup key.

Pros:
- keeps git clean of derived binary artifacts
- deterministic CI and deployment behavior
- simple invalidation via metadata and versioning
- easy to extend later to additional asset sets

Cons:
- adds Docker build work
- requires a small serialization format and lookup layer

### Option B: Build-time cache files stored next to production WAV files

Generate sibling files near the source WAVs in `biba-controller/voice/`.

Pros:
- simple path resolution

Cons:
- mixes source and derived assets
- makes format migrations and cleanup messier
- less clear separation of responsibilities

### Option C: Single packed cache manifest for all production voice assets

Generate one aggregate cache file containing all analyzed frames.

Pros:
- one file to load

Cons:
- harder per-file invalidation
- harder to inspect or regenerate incrementally
- unnecessary complexity for the current scale

## Recommendation

Use Option A.

Build the spectral cache into a dedicated directory inside the Docker image and keep runtime fallback to live analysis for any path not covered by the precomputed set. This gives the latency win where it matters, stays aligned with the existing deployment model, and avoids coupling the repository to derived audio-analysis outputs.

## Architecture

### Build-Time Spectral Cache

Add a build helper script under the controller tree that:
- scans the production voice directory `biba-controller/voice/`
- runs the same spectral analysis parameters currently used by `wav_to_peak_frames()`
- writes one cache artifact per WAV into a dedicated output directory
- writes metadata needed for cache validation

The Dockerfile should invoke this helper after the controller sources are copied into the image. A failed spectral build should fail the image build, because broken production voice assets should be caught in CI rather than discovered on the robot.

### Cache Format

Each cache entry should record:
- source relative path
- source file size
- source modification timestamp or content digest
- spectral parameter values
- explicit algorithm version
- analyzed frames

The format can start as JSON for transparency and testability. If size or parse time becomes material, the format can later move to a binary encoding without changing the runtime contract.

### Runtime Lookup Path

`MotorSynth.play_spectral()` should keep its public signature. Internally it should use a helper that:
- resolves whether the requested WAV belongs to the production voice set
- looks for a matching cache artifact in the spectral cache directory
- validates the cache metadata against the current source file and algorithm version
- loads cached frames when valid
- falls back to live `wav_to_peak_frames()` when no valid cache exists

Fallback is required so that:
- temporary test WAVs still work
- robot audition paths remain usable
- the system stays resilient if a cache artifact is missing

### Production Scope

The first implementation should precompute only production voice WAV assets. That keeps image size and build time bounded while addressing the current latency pain on arm, disarm, connected, disconnected, failsafe, low-voltage, startup, and SOS event audio.

Audition and staging assets can remain runtime-generated for now.

## BMS Latency Measurement Design

Add precise controller-side tracing on the BMS-to-telemetry path using monotonic timestamps. The trace should capture at least:
- fresh BMS state published by the poller
- battery telemetry payload assembled in main loop
- CRSF battery packet written to UART

These logs should be narrowly scoped and cheap enough for short diagnostic sessions. The goal is to measure component boundaries directly instead of inferring delay from throttled summary logs.

The first measurement target is controller-side latency only. If that proves small, the next stage can instrument Lua-side sensor refresh behavior separately.

## Testing Strategy

### Spectral Cache

- unit tests for cache serialization and deserialization
- unit tests for cache validation against metadata mismatch
- integration test proving build helper emits cache files for production WAVs
- integration test proving `MotorSynth.play_spectral()` loads cached frames when available
- fallback test proving uncached temp WAVs still use live analysis

### Docker Build Integration

- focused build-step test via direct helper invocation in pytest
- Dockerfile review to ensure the image build runs the helper deterministically

### BMS Trace

- tests for new trace helpers or logger formatting if logic is factored
- focused runtime tests proving telemetry send path can emit timestamped diagnostic lines without changing behavior

## Risks

- JSON cache artifacts may become larger than expected, increasing image size modestly.
- Source mtime inside Docker can be influenced by build context semantics; file digest may prove more robust than mtime.
- If algorithm constants change without version bump, stale cache could be used incorrectly.
- Additional trace logging must stay behind a targeted condition or low-volume path to avoid noisy normal operation.

## Success Criteria

- production voice events no longer spend seconds on runtime spectral preprocessing on the robot
- Docker image build deterministically regenerates spectral cache artifacts from the committed production WAV set
- runtime still works for uncached ad hoc WAV paths via fallback analysis
- controller logs can show exact BMS publish-to-UART timing for battery telemetry packets
- follow-up robot runs can distinguish controller delay from ELRS or radio-display delay