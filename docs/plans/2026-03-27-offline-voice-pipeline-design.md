# Offline Voice Pipeline Design

## Goal

Create an offline content-preparation pipeline that produces short, intelligible robot-voice WAV assets tailored for BiBa's motor-coil spectral playback path.

## Current State

The controller already supports grouped voice events, but the current priority is intelligibility. Default event groups should therefore carry one production WAV each, while content experimentation happens outside the runtime controller.

The active playback stack is:
- approved WAV asset
- spectral analysis in `biba-controller/buzzer/wav_player.py`
- motor-coil playback via `MotorSynth.play_spectral()`

That means the biggest leverage is not more runtime complexity, but better source material entering the existing channel.

## Constraints

- Runtime playback must stay simple and stable.
- The controller should not generate TTS on-device.
- Grouped selection remains supported, but default production config should use one asset per event for easier listening evaluation.
- Offline generation must be reproducible from source text or a seed WAV.
- Output should favor short command-like phrases over natural speech.
- Robot verification must respect the existing deployment workflow: candidates are committed to the repo and deployed via the robot-side update path rather than copied into the robot manually.

## Recommendation

Build an offline phrase factory separate from the controller runtime.

Recommended stages:
1. Source definition per event in a phrase manifest.
2. Offline generation from text using a compact formant-style TTS engine.
3. DSP post-processing tuned for the motor playback channel.
4. Batch export of several candidates per phrase.
5. Robot audition packaging and playback verification on hardware.
6. Human comparison of candidates based on the hardware playback result.
7. Manual promotion of one chosen WAV per event into `biba-controller/voice/`.

## Generator Choice

### Preferred: eSpeak NG or compatible offline formant TTS

Why:
- open-source and operationally straightforward
- offline WAV generation
- parameterized rate, pitch, and voice shaping
- good fit for short robotic commands

### Not recommended as a repo dependency: SAM ports

Why:
- useful as a style reference for retro robot speech
- licensing is unclear in commonly mirrored ports
- acceptable as inspiration, not as a direct project dependency

## Architecture

### Inputs

A manifest file, for example `voice-src/phrases.yml`, should describe:
- event key
- canonical phrase text
- optional alternate text
- optional seed WAV
- optional generation profile overrides

### Pipeline Stages

#### 1. Generation

For text inputs, produce raw WAV files using a configurable offline TTS backend.

Suggested baseline parameters:
- slower speaking rate than default
- controlled pitch range
- robotic or monotone voice when available

#### 2. Speech Conditioning

Prepare the speech before motor-specific degradation:
- trim silence
- normalize peak and loudness
- compress dynamic range
- slightly slow down phrase timing if needed
- emphasize consonant attacks conservatively

#### 3. Motor-Channel Shaping

Shape content for the spectral playback path:
- high-pass to remove muddy low end
- low-pass or band-limit to the range the motor channel reproduces best
- optional gentle saturation to increase harmonic persistence
- keep phrase length short enough for event feedback

#### 4. Variant Export

Export multiple candidate WAVs per event/profile combination into a working directory, for example:
- `voice-work/startup/`
- `voice-work/arm/`

Naming should encode profile choices so the winning asset can be traced back to its recipe.

#### 5. Robot Audition

Offline listening on a laptop is not enough. The pipeline must include a repeatable way to hear candidate assets through the real robot motors.

Recommended verification workflow:
- export candidate WAVs into a repo-tracked audition area such as `voice-work/robot-audition/<event>/`
- generate a small audition manifest describing playback order and source recipe
- deploy the updated repo to the robot through the normal `bbupdate` path
- trigger a robot-side audition command that plays the candidate list one by one through the existing spectral path
- record human notes about intelligibility after real hardware playback

The important rule is that robot audition is part of the content pipeline, not an ad hoc manual copy step.

#### 6. Promotion

Promotion into `biba-controller/voice/` stays manual in v1. This avoids accidental deployment of poor candidates and keeps human hardware listening in the loop.

## Robot Audition Approaches

### Option A: Replace production assets for each test run

Pros:
- simple to understand

Cons:
- noisy workflow
- easy to lose track of which candidate was tested
- mixes experimentation with production paths

### Option B: Dedicated audition directory and playback command

Pros:
- keeps production assets untouched until a winner is chosen
- preserves traceability from generated candidate to hardware test
- fits the existing safe deploy workflow

Cons:
- requires a small amount of support code for manifest reading and ordered playback

### Option C: Copy files directly onto the robot for testing

Pros:
- fastest raw loop

Cons:
- violates the desired deployment discipline
- creates configuration drift between repo and robot
- rejected for this project

## Recommendation for Robot Audition

Use Option B.

The offline pipeline should stage candidates in a dedicated audition area, deploy them via the repository, and invoke a robot-side playback helper that runs through the same motor spectral output path used in production. That gives realistic feedback while keeping the robot state reproducible.

## Profiles

The first version should support a small fixed profile set instead of arbitrary DSP graphs.

Suggested profiles:
- `command_slow`: slow, narrow-band, high clarity target
- `robot_harsh`: slightly more synthetic, more harmonic bite
- `seed_clean`: post-process an existing WAV without TTS generation

## Runtime Impact

Runtime code changes should be minimal:
- keep voice grouping support intact
- default to one production WAV per event
- no new runtime dependencies
- add only the minimum support needed for ordered audition playback on the robot

## Testing Strategy

### Controller

- configuration test proving one default voice asset per event

### Pipeline

When implemented:
- manifest parsing tests
- command construction tests for TTS backend invocation
- DSP recipe tests on generated fixture WAVs
- naming/output-path tests
- audition manifest tests
- ordered playback selection tests for robot audition mode

## Success Criteria

- defaults expose one production WAV per event
- offline content workflow is documented end-to-end
- pipeline can generate repeatable candidate sets for each event
- candidate sets can be played back on the robot through the real motor spectral path
- promotion of winning assets into runtime stays simple
- future expansion back to multi-voice groups remains possible through config overrides
