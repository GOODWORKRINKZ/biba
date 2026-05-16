# Phase 3: Field Ready - Research

**Researched:** 2026-05-16
**Domain:** Thermal protection, BTS7960 latch recovery, hardware-variant documentation, and field-validation planning for BiBa [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; .planning/ROADMAP.md]
**Confidence:** MEDIUM-HIGH [VERIFIED: local repo code/docs were inspected directly; MEDIUM because Phase 3 targets the RP2040 field-ready path while the repository also contains richer Pi-only runtime surfaces and the branch integration point is not fully locked in-repo] [VERIFIED: README.md; .planning/STATE.md] [ASSUMED]

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** For the brushed DC motor + BTS7960 configuration, thermal-fault recovery uses the BTS7960 enable/inhibit path, not a power-cut SSR. The prior SSR idea from Phase 1 is not required for this Phase 3 thermal-reset use case. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- **D-02:** Treat the module's `R_EN` and `L_EN` lines as the effective enable/disable path for the paired BTS7960 half-bridges. To clear a latched overtemperature shutdown, drive both enable lines LOW, then return them HIGH before motion is allowed again. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- **D-03:** The reset pulse is intentionally conservative: hold both enable lines LOW for **100 us**. Datasheet minimum is `treset >= 3 us`, but planning and implementation should not target the bare minimum. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- **D-04:** Run the enable-reset sequence during the arm initialization procedure for this BTS7960-based brushed-drive path. PWM must remain zero while enable is LOW and until enable returns HIGH. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- **D-05:** This reset sequence only clears the latch if the device has already cooled by at least the thermal hysteresis. Software must not assume that an immediate re-arm always succeeds after a real overtemperature event. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]

### the agent's Discretion
- Exact placement of the 100 us LOW pulse inside the arm/disarm state machine. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- Whether to add a short post-enable guard time before accepting non-zero PWM. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- Whether a failed recovery is surfaced as a log-only condition, a latched disarm, or a user-visible fault. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]

### Deferred Ideas (OUT OF SCOPE)
- Fallback behavior if the BTS7960 still does not recover after the enable-reset pulse: retry policy, permanent fault latch, or explicit operator feedback. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- Whether to log a dedicated thermal-latch recovery event for field validation runs. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- Whether non-brushed or non-BTS variants should keep SSR-based power cutting for unrelated reasons. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| THERM-01 | Программная защита: при превышении тока/температуры применяется throttle back. [VERIFIED: .planning/REQUIREMENTS.md] | Existing software throttle-back already exists in both the Python controller and firmware standalone loop, so planning should treat this as alignment and validation work plus BTS latch-recovery integration, not a greenfield limiter. [VERIFIED: biba-controller/motors/current_control.py; biba-controller/main.py; firmware/src/modes/mode_standalone.c] |
| THERM-02 | Аппаратная теплоотводящая пластина под BTS7960 установлена (hardware task). [VERIFIED: .planning/REQUIREMENTS.md] | Repo state already records heat-sink work in progress and a field failure caused by ESC thermal mode, so the plan must include a hardware/documentation/field-evidence task, not only code. [VERIFIED: .planning/STATE.md; .planning/PROJECT.md] |
| VARIANT-01 | Документирована таблица вариантов: плата × тип мотора × тип драйвера × опциональные модули. [VERIFIED: .planning/REQUIREMENTS.md] | Repo docs already describe Pi Zero 2W, STM32F103, and RP2040 variants in scattered places, but there is no single canonical matrix with status and implementation links. [VERIFIED: README.md; docs/system_architecture.md; docs/wiring.md; firmware/README.md] |
| VARIANT-02 | Каждый вариант имеет статус (ready / WIP / planned) и ссылку на target.md или ветку. [VERIFIED: .planning/REQUIREMENTS.md] | STM32 and RP2040 already have target/build surfaces, and README already references `rp2040-port`, but Pi-only lacks a `target.md`-style canonical implementation card, so the plan must define what qualifies as the Pi-only reproducible link. [VERIFIED: firmware/targets/RPICO_RP2040/target.md; firmware/targets/BLUEPILL_F103C8/target.md; firmware/targets/BIBA_F103_REV_A/target.md; README.md] |
</phase_requirements>

## Project Constraints (from copilot-instructions.md)

- No repo-root `copilot-instructions.md` exists, so there are no additional project-local instruction overrides beyond the repository files and skills inspected in this session. [VERIFIED: file search for `/home/ros2/Downloads/biba/copilot-instructions.md` returned no file]
- Repo-local skills indicate code plans should assume test-first changes before production edits. [VERIFIED: .agents/skills/test-driven-development/SKILL.md]
- Repo-local skills require fresh executable verification before claiming completion, so every implementation plan should end with explicit test/build evidence rather than doc-only assertions. [VERIFIED: .agents/skills/verification-before-completion/SKILL.md]
- Repo-local planning guidance expects small, exact tasks with explicit file targets and commands, which matters because Phase 3 naturally splits into several independent plan slices. [VERIFIED: .agents/skills/writing-plans/SKILL.md]

## Summary

Phase 3 should be planned as four separate but coordinated slices: thermal-latch recovery in the owning BTS7960 driver/HAL path, current-limit validation and threshold tuning, a canonical hardware-variant matrix document, and a field-validation evidence package. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; biba-controller/motors/driver.py; biba-controller/main.py; firmware/src/modes/mode_standalone.c; README.md; docs/system_architecture.md; artifacts/current-trace]

The most important planning correction is that the repository still contains older SSR-based assumptions in the RP2040/firmware path, while the new Phase 3 context explicitly supersedes that approach for brushed BTS7960 thermal-latch recovery. The Phase 1 context says SSR cuts power on arm/disarm and that EN pins stay high after boot, but Phase 3 now locks recovery to the BTS7960 enable/inhibit path instead. Any plan that carries Phase 1 SSR behavior forward for this use case will be wrong. [VERIFIED: .planning/phases/01-core-drive/01-CONTEXT.md; .planning/phases/03-field-ready/03-CONTEXT.md; firmware/src/modes/mode_standalone.c]

The repo already has substantial reusable protection and validation surfaces. The Python controller owns independent current limiting, BMS freshness tracking, current-trace JSONL logging, and broad pytest coverage. The firmware standalone loop already mirrors per-motor current limiting and owns enable pins through `biba_bts7960_set_enabled()`, but it still initializes the motor path with old semantics and no Phase 3 enable-reset primitive. That means Phase 3 is a focused integration/refinement phase, not a blank-sheet safety system. [VERIFIED: biba-controller/motors/current_control.py; biba-controller/motors/current_sense.py; biba-controller/bms/poller.py; tests/test_current_control.py; tests/test_current_sense.py; tests/test_bms_poller.py; tests/test_main.py; firmware/src/drivers/bts7960.c; firmware/src/modes/mode_standalone.c; firmware/src/hal/biba_hal_rp2040.c]

**Primary recommendation:** Plan Phase 3 around one canonical BTS7960 recovery contract, implemented at the enable-pin owner, then validate it with existing limiter/trace tooling and publish a single hardware matrix that points each supported variant at either `target.md`, compose docs, or an explicit branch reference. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; biba-controller/motors/driver.py; firmware/src/drivers/bts7960.c; README.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Clear a latched BTS7960 thermal shutdown on arm | Motor-driver / HAL tier [VERIFIED: biba-controller/motors/driver.py; firmware/src/drivers/bts7960.c; firmware/src/hal/biba_hal_rp2040.c] | Arm/disarm control-loop tier [VERIFIED: biba-controller/main.py; firmware/src/modes/mode_standalone.c] | The enable lines are already owned by driver/HAL code, so the arm state machine should trigger a reset primitive rather than re-implement GPIO sequencing inline. [VERIFIED: biba-controller/motors/driver.py; firmware/src/drivers/bts7960.c] |
| Prevent thermal escalation during drive | Current-limit / control-loop tier [VERIFIED: biba-controller/main.py; biba-controller/motors/current_control.py; firmware/src/modes/mode_standalone.c] | Field-test / tuning tier [VERIFIED: docs/plans/2026-03-30-current-sense-calibration-trace-design.md; artifacts/current-trace] | The existing limiter already scales requested outputs from measured current, but threshold selection and proof that it protects the real hardware are field-validation work. [VERIFIED: tests/test_current_control.py; tests/test_main.py] |
| Prove THERM-02 hardware heat-sink readiness | Physical hardware tier [VERIFIED: .planning/REQUIREMENTS.md; .planning/STATE.md] | Field-artifact / documentation tier [VERIFIED: docs/telemetry-investigation-2026-03-28.md; artifacts/current-trace; artifacts/telemetry-captures] | The hardware plate itself cannot be validated in code; the repo can only capture and organize the evidence and acceptance criteria. [VERIFIED: .planning/ROADMAP.md; .planning/PROJECT.md] |
| Publish supported hardware variants with statuses and links | Documentation tier [VERIFIED: README.md; docs/system_architecture.md; docs/wiring.md; firmware/README.md] | Build-target / branch-reference tier [VERIFIED: firmware/platformio.ini; firmware/targets/*/target.md; README.md] | The information already exists but is fragmented; the owner should be a single canonical matrix doc backed by existing target/build files rather than more scattered prose. [VERIFIED: README.md; firmware/README.md; docs/system_architecture.md] |
| Preserve field-validation evidence | Artifact / logging tier [VERIFIED: biba-controller/main.py; biba-controller/bms/poller.py; docs/telemetry-investigation-2026-03-28.md] | Operator procedure tier [VERIFIED: artifacts/current-trace; artifacts/telemetry-captures] | Existing capture tools and JSONL traces already give a place to store evidence, but the planner still needs a repeatable field-test procedure and naming convention. [VERIFIED: tests/test_vcp_capture.py; tests/test_main.py] |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `biba-controller` BTS7960 path (`BTS7960MotorDriver`, `DifferentialDrive`, `main.py`) | in-repo module, no external version pin [VERIFIED: biba-controller/motors/driver.py; biba-controller/main.py] | Existing Pi-only runtime owns REN/LEN pins, current limiting, arm/disarm gating, and current trace logging. [VERIFIED: biba-controller/motors/driver.py; biba-controller/main.py] | Reusing the owning runtime avoids duplicating enable semantics elsewhere. [VERIFIED: biba-controller/motors/driver.py] |
| Firmware standalone drive path (`mode_standalone.c`, `bts7960.c`, RP2040 HAL) | in-repo source, built via PlatformIO envs [VERIFIED: firmware/src/modes/mode_standalone.c; firmware/src/drivers/bts7960.c; firmware/platformio.ini] | Existing RP2040/STM32-side low-level owner of enable pins, CRSF failsafe, ramping, and current limiting. [VERIFIED: firmware/src/modes/mode_standalone.c; firmware/src/drivers/bts7960.c] | Phase 3 recovery semantics belong here for the embedded field-ready path. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md] |
| Per-motor current limiter (`apply_motor_limits` / `biba_apply_motor_limits`) | in-repo source [VERIFIED: biba-controller/motors/current_control.py; firmware/src/app/control_loop.h; firmware/src/modes/mode_standalone.c] | Implements throttle-back instead of hard stop under current overload. [VERIFIED: biba-controller/motors/current_control.py; firmware/src/modes/mode_standalone.c] | This already matches THERM-01 intent closely enough that planning should tune and validate it rather than replace it. [VERIFIED: .planning/REQUIREMENTS.md; tests/test_current_control.py; tests/test_main.py] |
| PlatformIO Core | `6.1.19` [VERIFIED: local `pio --version`] | Firmware build/test entrypoint for RP2040 and STM32 targets. [VERIFIED: firmware/README.md; firmware/platformio.ini] | Required for any embedded slice of Phase 3. [VERIFIED: firmware/README.md] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | `6.2.5` via `python3 -m pytest` in this environment; repo dev requirement is `>=8,<9` [VERIFIED: local `python3 -m pytest --version`; requirements-dev.txt] | Focused validation for Python controller, docs/config structure, and trace helpers. [VERIFIED: pytest.ini; tests/test_motors.py; tests/test_main.py; tests/test_config.py] | Use for Pi-only runtime slices and documentation/config regression checks. [VERIFIED: tests/] |
| `pigpio` | unpinned in repo requirements [VERIFIED: biba-controller/requirements.txt] | GPIO/PWM ownership on Pi-only runtime. [VERIFIED: biba-controller/motors/driver.py] | Use only where Phase 3 touches the Python controller motor path. [VERIFIED: biba-controller/main.py] |
| `smbus2` | unpinned in repo requirements [VERIFIED: biba-controller/requirements.txt] | ADS1115 current-sense backend. [VERIFIED: biba-controller/motors/current_sense.py] | Use for current-limit calibration and field-trace evidence, not for thermal-latch reset itself. [VERIFIED: docs/plans/2026-03-30-current-sense-calibration-trace-design.md] |
| `PyYAML` | `>=6,<7` [VERIFIED: biba-controller/requirements.txt; requirements-dev.txt] | Structural tests over config and launch YAML surfaces. [VERIFIED: tests/test_biba_bringup_control.py] | Useful for variant-matrix docs or config scaffolding if Phase 3 adds generated metadata. [ASSUMED] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| EN/INH recovery pulse on `REN`/`LEN` [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md] | SSR power cut from old Phase 1 design [VERIFIED: .planning/phases/01-core-drive/01-CONTEXT.md] | Phase 3 context explicitly supersedes the SSR approach for this brushed BTS7960 thermal-latch use case, so keeping SSR in scope for reset would preserve the wrong contract. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md] |
| Single canonical variant matrix doc [VERIFIED: .planning/REQUIREMENTS.md] | Continue scattering variant info across README, wiring, deployment, and target docs [VERIFIED: README.md; docs/wiring.md; docs/deployment.md; firmware/README.md] | The scattered approach already contains most facts but does not satisfy `VARIANT-01`/`VARIANT-02` as a reviewable artifact. [VERIFIED: .planning/REQUIREMENTS.md] |
| Existing current trace JSONL and telemetry captures [VERIFIED: biba-controller/main.py; artifacts/current-trace; artifacts/telemetry-captures] | Ad-hoc operator notes or log scraping after the fact | Existing trace surfaces preserve timestamps and current samples in machine-readable form, which is better for field proof and tuning. [VERIFIED: docs/plans/2026-03-30-current-sense-calibration-trace-design.md; tests/test_vcp_capture.py; tests/test_main.py] |

**Installation:**
```bash
python3 -m pip install -r requirements-dev.txt
cd firmware && pio test -e native_test
```

**Version verification:** `pio --version` returned `PlatformIO Core, version 6.1.19`; `python3 -m pytest --version` returned `pytest 6.2.5`; Python is `3.10.12`. [VERIFIED: local terminal probes]

## Architecture Patterns

### System Architecture Diagram

```text
RC / operator input
	|
	v
Arm / disarm state machine
	|
	+--> on arm edge: BTS7960 enable-reset primitive
	|         |
	|         +--> EN LOW for 100 us
	|         +--> EN HIGH
	|         +--> optional post-enable PWM guard
	|
	v
Mix / ramp / assist
	|
	v
Current sense ------> current limiter ------> trim / output gate ------> BTS7960 PWM
	|                       |                                           |
	|                       +--> THERM-01 throttle-back evidence        +--> real motor behavior
	|
	+--> trace / telemetry artifacts --> JSONL + VCP/log captures --> field report

Variant docs inputs: README + wiring + deployment + target.md + branch refs
	|
	v
Canonical Phase 3 hardware matrix
```

This diagram reflects the actual repo surfaces: control and current-limit code are already in the loop, and the missing pieces are the Phase 3 enable-reset contract, canonical variant documentation, and explicit field-validation evidence packaging. [VERIFIED: biba-controller/main.py; firmware/src/modes/mode_standalone.c; README.md; docs/wiring.md; firmware/targets/*/target.md]

### Recommended Project Structure
```text
.planning/phases/03-field-ready/
├── 03-RESEARCH.md          # this document
├── 03-01-PLAN.md           # thermal reset integration and tests
├── 03-02-PLAN.md           # limiter threshold/alignment + trace validation
├── 03-03-PLAN.md           # canonical hardware matrix docs
└── 03-04-PLAN.md           # field-test procedure + evidence capture

docs/
├── wiring.md               # low-level pin truth, kept as source input
├── deployment.md           # Pi-only reproducibility link/source input
├── system_architecture.md  # composition truth/source input
└── variants.md             # recommended new canonical matrix output [ASSUMED]
```

### Pattern 1: Driver-Owned Enable Reset Primitive
**What:** Add a single BTS7960 reset primitive where the enable pins are already owned, and invoke it from arm initialization rather than from higher-level code. [VERIFIED: biba-controller/motors/driver.py; firmware/src/drivers/bts7960.c; .planning/phases/03-field-ready/03-CONTEXT.md]
**When to use:** Whenever a BTS7960-based brushed path needs a thermal-latch clear before motion can resume. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
**Example:**
```python
# Source: biba-controller/motors/driver.py + Phase 3 context
for pin in self._unique_pins(self.ren_pin, self.len_pin):
	self.pi.write(pin, 1)

# Phase 3 should extend this owner with a reset method that drives both
# enable pins LOW, keeps PWM zero, then restores HIGH before drive output.
```

### Pattern 2: Current Limiter Before Field Claims
**What:** Keep using the existing per-motor limiter as the software throttle-back mechanism, and prove the chosen thresholds with captured traces instead of guessing. [VERIFIED: biba-controller/motors/current_control.py; biba-controller/main.py; docs/plans/2026-03-30-current-sense-calibration-trace-design.md]
**When to use:** For THERM-01 acceptance and any field test where BTS7960 overheating risk is being reduced by current limiting. [VERIFIED: .planning/REQUIREMENTS.md; .planning/ROADMAP.md]
**Example:**
```python
# Source: biba-controller/motors/current_control.py
if config.current_limit_a > 0.0 and current_a > config.current_limit_a:
	scale = min(scale, config.current_limit_a / current_a)
```

### Pattern 3: Docs Matrix Built From Existing Truth Sources
**What:** Build one explicit matrix from README, wiring, deployment, target docs, and branch references instead of inventing a second source of truth. [VERIFIED: README.md; docs/wiring.md; docs/deployment.md; docs/system_architecture.md; firmware/README.md]
**When to use:** For `VARIANT-01` and `VARIANT-02`. [VERIFIED: .planning/REQUIREMENTS.md]
**Example:**
```text
platform | control owner | motor driver | optional modules | status | implementation link
Pi Zero 2W | biba-controller | dual BTS7960 | ADS1115, IMU, BMS, voice | ready | docker/legacy-pi + docs/deployment.md
RP2040 | firmware env rpico_rp2040_standalone | BTS7960 | IMU/current sense/trim | WIP | firmware/targets/RPICO_RP2040/target.md + rp2040-port branch
STM32F103 | firmware standalone/companion/combined | BTS7960 | IMU/current sense/SPI add-on | ready/WIP by target | target.md
```

### Anti-Patterns to Avoid
- **Carrying SSR reset semantics into Phase 3:** The new context supersedes this for the brushed BTS7960 thermal-latch case. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; .planning/phases/01-core-drive/01-CONTEXT.md]
- **Driving PWM during EN-low or immediately after EN-high without an explicit guard decision:** The context requires PWM zero while disabled and leaves the post-enable guard as a planning choice. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
- **Promising software temperature regulation without a decoded temperature source:** The repo has current-based limiting today, and only one STM32 target exposes a chassis NTC hook that is explicitly not decoded yet. [VERIFIED: biba-controller/main.py; firmware/targets/BIBA_F103_REV_A/target.h; firmware/src/drivers/voltage_sense.c]
- **Treating scattered docs as a finished variant matrix:** The repo has many inputs, but not the Phase 3 output artifact. [VERIFIED: README.md; docs/system_architecture.md; docs/wiring.md; firmware/README.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Clearing a BTS7960 thermal latch | New SSR-based reset path or ad-hoc GPIO toggles inside the main loop | A driver/HAL-owned enable-reset primitive on `REN`/`LEN` | The pins are already owned there, and Phase 3 explicitly locks recovery to EN/INH semantics. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; biba-controller/motors/driver.py; firmware/src/drivers/bts7960.c] |
| Software throttle-back | New thermal-control algorithm from scratch | Existing per-motor current limiter plus threshold tuning | The repo already has validated limiter behavior and trace infrastructure for evidence. [VERIFIED: biba-controller/motors/current_control.py; tests/test_current_control.py; tests/test_main.py; firmware/src/modes/mode_standalone.c] |
| Field telemetry capture | Manual copy/paste from console logs | Existing JSONL current trace and VCP capture tooling | Existing capture formats preserve timestamps and current samples in a reusable way. [VERIFIED: biba-controller/main.py; scripts/vcp_capture.py; tests/test_vcp_capture.py; docs/telemetry-investigation-2026-03-28.md] |
| Variant inventory | Another prose-heavy architecture overview | One canonical status matrix linking existing docs/build targets | The inputs already exist; the missing deliverable is consolidation. [VERIFIED: README.md; docs/system_architecture.md; docs/deployment.md; docs/wiring.md; firmware/README.md] |

**Key insight:** Phase 3 should mostly compose and align existing mechanisms, not invent new subsystems. The only genuinely new control behavior is the canonical EN-low thermal reset contract and its failure handling. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; biba-controller/main.py; firmware/src/modes/mode_standalone.c]

## Common Pitfalls

### Pitfall 1: Planning Against The Wrong Historical Contract
**What goes wrong:** A plan reuses the old Phase 1 SSR reset story and leaves EN pins permanently high. [VERIFIED: .planning/phases/01-core-drive/01-CONTEXT.md]
**Why it happens:** The repository still contains that older context and firmware code paths that call `biba_hal_ssr_set(armed)`. [VERIFIED: firmware/src/modes/mode_standalone.c]
**How to avoid:** Treat `03-CONTEXT.md` as the Phase 3 source of truth and schedule any SSR clean-up or divergence explicitly. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
**Warning signs:** Plans mention “remote thermal reset via SSR” for brushed BTS7960 recovery. [VERIFIED: .planning/phases/01-core-drive/01-CONTEXT.md]

### Pitfall 2: Confusing Current Protection With Temperature Measurement
**What goes wrong:** The plan promises temperature-based throttle-back or thermal state estimation without a decoded thermal input. [VERIFIED: .planning/REQUIREMENTS.md]
**Why it happens:** The repo already has current limiting, BMS battery temperatures, and a future chassis NTC hook, which can look like a complete thermal-control stack when it is not. [VERIFIED: biba-controller/main.py; biba-controller/bms/daly.py; firmware/targets/BIBA_F103_REV_A/target.h; firmware/src/drivers/voltage_sense.c]
**How to avoid:** Scope THERM-01 around existing current-based throttle-back plus BTS latch recovery unless a real motor-driver temperature signal is deliberately added in a separate plan. [VERIFIED: biba-controller/motors/current_control.py; .planning/phases/03-field-ready/03-CONTEXT.md]
**Warning signs:** A task list mentions “read BTS temperature” but names no actual hardware signal or decoding path. [VERIFIED: repo grep showed no BTS temperature decode path in current controller/firmware]

### Pitfall 3: No Explicit Zero-PWM Invariant During Recovery
**What goes wrong:** The controller toggles EN lines but still allows stale or queued PWM to reach the bridge. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]
**Why it happens:** Existing code already has multiple stages of drive gating, audio gating, and ramping, so it is easy to add the reset pulse in the wrong place. [VERIFIED: biba-controller/main.py; firmware/src/modes/mode_standalone.c]
**How to avoid:** Make the reset primitive responsible for driving PWM to zero or ensure the arm state machine enforces zero output around the primitive, and add a regression test for non-zero PWM rejection until recovery completes. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; tests/test_motors.py; tests/test_main.py]
**Warning signs:** Implementation notes talk only about pin pulses, not about output gating or race-free sequencing. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]

### Pitfall 4: Treating Field Readiness As Only A Code Change
**What goes wrong:** Phase 3 is marked complete after code/tests/docs, without a hardware plate installation record or a captured field run. [VERIFIED: .planning/ROADMAP.md; .planning/REQUIREMENTS.md]
**Why it happens:** The repo has strong software test coverage, but THERM-02 and the 30-minute success criterion are physical-world checks. [VERIFIED: .planning/ROADMAP.md; tests/test_main.py; tests/test_current_control.py]
**How to avoid:** Make the field protocol, artifact names, and acceptance evidence a first-class plan output. [VERIFIED: artifacts/current-trace; artifacts/telemetry-captures; docs/telemetry-investigation-2026-03-28.md]
**Warning signs:** No artifact path, no test-duration definition, and no hardware/photo/log checklist appear in the plan. [VERIFIED: current repo lacks a dedicated Phase 3 field-test artifact doc]

### Pitfall 5: Shipping Another Fragmented Variant Story
**What goes wrong:** The planner edits README or wiring in isolation and still leaves reviewers unable to answer “which variants are supported, with what status, and where is the canonical implementation link?” [VERIFIED: README.md; docs/wiring.md; docs/system_architecture.md; firmware/README.md]
**Why it happens:** Repo docs already contain overlapping but differently scoped variant descriptions. [VERIFIED: README.md; docs/system_architecture.md; docs/deployment.md; firmware/README.md]
**How to avoid:** Pick one canonical matrix artifact and make the other docs link to it rather than re-describing statuses independently. [VERIFIED: .planning/REQUIREMENTS.md]
**Warning signs:** Status words like `ready`, `WIP`, and `planned` appear in multiple docs but not in one reviewable table. [VERIFIED: README.md; .planning/PROJECT.md; .planning/ROADMAP.md]

## Code Examples

Verified patterns from the repository:

### Current-Limit Throttle Back
```python
# Source: biba-controller/main.py + motors/current_control.py
limited = _limit_drive_outputs(
	requested_left=requested_left,
	requested_right=requested_right,
	left_sample=left_sample,
	right_sample=right_sample,
	battery_state=battery_state,
)
trimmed_left, trimmed_right = _apply_motor_trim(
	limited.left_output,
	limited.right_output,
	motor_trim,
)
```

This is the existing THERM-01-shaped pattern in the Python runtime: requested output is limited first, then trim is applied, then the final values are sent to the motor driver. [VERIFIED: biba-controller/main.py]

### Firmware Enable Ownership
```c
// Source: firmware/src/drivers/bts7960.c
void biba_bts7960_set_enabled(bool enabled)
{
	biba_hal_left_enable(enabled);
	biba_hal_right_enable(enabled);
	if (!enabled) {
		biba_hal_motor_pwm_left(0.0f);
		biba_hal_motor_pwm_right(0.0f);
	}
}
```

This is the natural firmware-level insertion point for a Phase 3 reset primitive because it already owns both enable lines and the zero-PWM behavior when disabled. [VERIFIED: firmware/src/drivers/bts7960.c]

### BMS Freshness For Field Evidence
```python
# Source: biba-controller/bms/poller.py
with self._lock:
	self._state = state
	self._state_timestamp_s = polled_at_s
```

This existing timestamp is what makes current traces useful for field correlation instead of only giving static samples. [VERIFIED: biba-controller/bms/poller.py; biba-controller/main.py]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSR power cut as the thermal-reset mechanism for brushed BTS7960 [VERIFIED: .planning/phases/01-core-drive/01-CONTEXT.md] | EN/INH reset on `REN`/`LEN` with a 100 us low pulse [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md] | Phase 3 context dated 2026-05-16 [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md] | Planning must now center on enable-pin semantics and likely remove or isolate old SSR assumptions in the embedded path. [VERIFIED: firmware/src/modes/mode_standalone.c] |
| Sparse ad-hoc battery logs for field interpretation [VERIFIED: docs/telemetry-investigation-2026-03-28.md] | JSONL current trace plus VCP capture artifacts [VERIFIED: biba-controller/main.py; scripts/vcp_capture.py; artifacts/current-trace; artifacts/telemetry-captures] | March 2026 trace/logging work [VERIFIED: docs/plans/2026-03-30-current-sense-calibration-trace-design.md; docs/telemetry-investigation-2026-03-28.md] | Phase 3 can demand objective field evidence instead of only subjective driving notes. [VERIFIED: tests/test_main.py; tests/test_vcp_capture.py] |
| Fragmented hardware descriptions across several docs [VERIFIED: README.md; docs/system_architecture.md; docs/wiring.md; firmware/README.md] | Still fragmented; no canonical status matrix yet [VERIFIED: repo inspection in this session] | Not changed yet [VERIFIED: .planning/REQUIREMENTS.md] | VARIANT-01/02 remain unmet until one canonical matrix is published. [VERIFIED: .planning/REQUIREMENTS.md] |

**Deprecated/outdated:**
- Old SSR-based thermal-reset planning for the brushed BTS7960 Phase 3 path is outdated for this specific use case. [VERIFIED: .planning/phases/01-core-drive/01-CONTEXT.md; .planning/phases/03-field-ready/03-CONTEXT.md]

## Resolved Planning Decisions

The previous open questions are resolved for Phase 3 planning and no blocking research decisions remain.

1. **Authoritative implementation surface for THERM-01 thermal-reset behavior:**
	- Decision: Use the firmware implementation in this workspace as the source of truth for Phase 3 plan execution. `rp2040-port` remains a reference/link artifact for variant documentation only.
	- Evidence: `firmware/platformio.ini` defines active RP2040 envs in this workspace and Phase 3 plans target these files directly. [VERIFIED: firmware/platformio.ini; .planning/phases/03-field-ready/03-01-PLAN.md]

2. **Canonical implementation link for Pi Zero 2W row in `VARIANT-02`:**
	- Decision: Use `docs/deployment.md` as the canonical implementation link for the Pi-only variant row in `docs/variants.md`.
	- Evidence: Pi deployment flow is documented there and is stable in this repo. [VERIFIED: docs/deployment.md]

3. **Minimum evidence for field-test PASS (THERM-02):**
	- Decision: PASS requires all of the following: heat-sink installation evidence recorded, completed 30-minute intensive drive protocol, required artifacts present under `artifacts/current-trace/` and `artifacts/telemetry-captures/`, and no unrecovered BTS7960 thermal latch during the run.
	- Evidence: This aligns ROADMAP success criteria with plan outputs in the field-validation and UAT plans. [VERIFIED: .planning/ROADMAP.md; .planning/phases/03-field-ready/03-02-PLAN.md; .planning/phases/03-field-ready/03-03-PLAN.md]

4. **How failed immediate recovery is surfaced after EN reset pulse (D-05 scope):**
	- Decision: For Phase 3, treat immediate non-recovery as a best-effort reset outcome and capture it through existing validation/UAT evidence flow; do not add new retry/fault-latch feature work in this phase.
	- Evidence: D-05 warns against guaranteed immediate recovery, and fallback policy is explicitly deferred. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md]

## Assumptions Log

No unresolved planning assumptions remain after the above resolutions.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3` | Python runtime/tests/docs scripts | ✓ [VERIFIED: local terminal probe] | `3.10.12` [VERIFIED: local terminal probe] | — |
| `pytest` entrypoint | Narrow Python test commands in docs/plans | ✗ as shell command [VERIFIED: local `command -v pytest`] | — | Use `python3 -m pytest` instead. [VERIFIED: local `python3 -m pytest --version`] |
| `python3 -m pytest` | Python verification in this workspace | ✓ [VERIFIED: local terminal probe] | `6.2.5` [VERIFIED: local terminal probe] | — |
| `pio` | Firmware builds/tests for RP2040/STM32 slices | ✓ [VERIFIED: local terminal probe] | `6.1.19` [VERIFIED: local terminal probe] | — |
| Physical robot + BTS7960 + heat sink + radio | THERM-02 and field validation | ✗ not available in the workspace tooling context [VERIFIED: this session only has code/artifact access] | — | None for true field readiness; bench or CI can validate software only. [VERIFIED: .planning/ROADMAP.md] |

**Missing dependencies with no fallback:**
- Real robot hardware for the heat-sink installation proof and the 30-minute thermal field test. [VERIFIED: .planning/REQUIREMENTS.md; .planning/ROADMAP.md]

**Missing dependencies with fallback:**
- Shell `pytest` command is missing, but `python3 -m pytest` works and should be used in plans. [VERIFIED: local terminal probes]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no [VERIFIED: Phase 3 scope is motor protection/docs/field validation, not user auth] | — |
| V3 Session Management | no [VERIFIED: same scope reasoning] | — |
| V4 Access Control | yes, at the actuation-control level rather than web auth [VERIFIED: arm/disarm gating in biba-controller/main.py; firmware/src/modes/mode_standalone.c] | Arm/disarm thresholds, failsafe gating, and zero-output behavior when disarmed. [VERIFIED: biba-controller/main.py; firmware/src/modes/mode_standalone.c] |
| V5 Input Validation | yes [VERIFIED: config parsing and channel normalization are part of the active control path] | Existing env parsers, clamp helpers, and channel normalization should remain the gate for any new thresholds or reset configuration. [VERIFIED: biba-controller/config.py; firmware/src/modes/mode_standalone.c] |
| V6 Cryptography | no [VERIFIED: no crypto requirement in this phase scope] | — |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Non-zero actuation during or immediately after thermal reset | Tampering / Safety fault | Keep PWM zero while EN is LOW and until recovery completes; enforce through the arm/control gate and tests. [VERIFIED: .planning/phases/03-field-ready/03-CONTEXT.md; biba-controller/main.py; firmware/src/drivers/bts7960.c] |
| Stale RC or stale upstream state causing unwanted motion | Denial of service / Safety fault | Existing failsafe and disarm paths must remain authoritative around any new reset behavior. [VERIFIED: biba-controller/main.py; firmware/src/app/failsafe.h; firmware/src/modes/mode_standalone.c] |
| Unbounded field-trace logging filling storage | Denial of service | Keep trace off by default and use the existing write gate and optional rate limit. [VERIFIED: biba-controller/config.py; biba-controller/main.py; tests/test_config.py] |
| Misconfigured variant metadata leading to unreproducible builds | Tampering / Integrity | Link each matrix row to an existing `target.md`, compose path, or explicit branch reference. [VERIFIED: firmware/targets/*/target.md; README.md; docs/deployment.md] |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/03-field-ready/03-CONTEXT.md` - locked Phase 3 thermal reset decisions and scope. [VERIFIED]
- `biba-controller/motors/driver.py` - current Pi-side BTS7960 enable ownership. [VERIFIED]
- `biba-controller/main.py` - arm/disarm flow, limiter wiring, BMS freshness, current-trace writes. [VERIFIED]
- `biba-controller/motors/current_control.py` and `biba-controller/motors/current_sense.py` - current throttle-back behavior and sensor model. [VERIFIED]
- `biba-controller/bms/poller.py` - timestamped BMS freshness support. [VERIFIED]
- `firmware/src/drivers/bts7960.c`, `firmware/src/modes/mode_standalone.c`, `firmware/src/hal/biba_hal_rp2040.c` - embedded enable semantics, current limiting, and existing SSR usage. [VERIFIED]
- `README.md`, `docs/system_architecture.md`, `docs/wiring.md`, `docs/deployment.md`, `firmware/README.md`, `firmware/targets/*/target.md` - existing variant documentation surfaces. [VERIFIED]
- `tests/test_motors.py`, `tests/test_current_control.py`, `tests/test_current_sense.py`, `tests/test_bms_poller.py`, `tests/test_main.py`, `tests/test_config.py`, `tests/test_vcp_capture.py` - reusable validation surfaces. [VERIFIED]

### Secondary (MEDIUM confidence)
- `.planning/PROJECT.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md` - roadmap and readiness framing used to shape plan seams and acceptance criteria. [VERIFIED]
- `docs/plans/2026-03-30-current-sense-calibration-trace-design.md` and `docs/telemetry-investigation-2026-03-28.md` - evidence practices for trace-based field validation. [VERIFIED]

### Tertiary (LOW confidence)
- None. All substantive technical claims in this research are tied to inspected repo files, except the explicit assumptions listed in the Assumptions Log. [VERIFIED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - existing code, requirements, and local tool availability were inspected directly. [VERIFIED]
- Architecture: MEDIUM - the core control responsibilities are clear, but the authoritative Phase 3 implementation branch remains slightly ambiguous. [VERIFIED] [ASSUMED]
- Pitfalls: HIGH - most pitfalls come from direct contradictions between old and new context or from inspected code/doc fragmentation. [VERIFIED]

**Research date:** 2026-05-16
**Valid until:** 2026-06-15 for repo-shape facts; re-check sooner if the `rp2040-port` branch or Phase 3 context changes. [VERIFIED: README.md] [ASSUMED]
