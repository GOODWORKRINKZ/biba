# Phase 3: Field Ready - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Field readiness for the RP2040/BTS7960 brushed-drive configuration: thermal protection behavior,
hardware variant documentation, and field validation. This discussion focused on how a BTS7960
thermal latch is cleared in the brushed-motor path and whether a dedicated SSR is still needed.

</domain>

<decisions>
## Implementation Decisions

### BTS7960 Thermal Latch Recovery
- **D-01:** For the brushed DC motor + BTS7960 configuration, thermal-fault recovery uses the BTS7960
  enable/inhibit path, not a power-cut SSR. The prior SSR idea from Phase 1 is not required for this
  Phase 3 thermal-reset use case.
- **D-02:** Treat the module's `R_EN` and `L_EN` lines as the effective enable/disable path for the paired
  BTS7960 half-bridges. To clear a latched overtemperature shutdown, drive both enable lines LOW,
  then return them HIGH before motion is allowed again.
- **D-03:** The reset pulse is intentionally conservative: hold both enable lines LOW for **100 us**.
  Datasheet minimum is `treset >= 3 us`, but planning and implementation should not target the bare
  minimum.
- **D-04:** Run the enable-reset sequence during the arm initialization procedure for this BTS7960-based
  brushed-drive path. PWM must remain zero while enable is LOW and until enable returns HIGH.
- **D-05:** This reset sequence only clears the latch if the device has already cooled by at least the
  thermal hysteresis. Software must not assume that an immediate re-arm always succeeds after a real
  overtemperature event.

### the agent's Discretion
- Exact placement of the 100 us LOW pulse inside the arm/disarm state machine.
- Whether to add a short post-enable guard time before accepting non-zero PWM.
- Whether a failed recovery is surfaced as a log-only condition, a latched disarm, or a user-visible fault.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Phase 3 scope and success criteria for thermal protection and field readiness
- `.planning/REQUIREMENTS.md` — `THERM-01`, `THERM-02`, `VARIANT-01`, `VARIANT-02`

### BTS7960 behavior and wiring
- `artifacts/datasheets/infineon-bts7960-ds-en.pdf` — official Infineon datasheet; overtemperature shutdown is latched and is reset via `INH LOW` with `treset >= 3 us`
- `docs/wiring.md` — current BTS7960 wiring and the existing `REN` / `LEN` pin naming used in this repo
- `docs/plans/2026-03-25-bts7960-design.md` — repository-level BTS7960 control model and enable-pin semantics

### Existing code and prior context
- `biba-controller/motors/driver.py` — current Python BTS7960 driver initializes `REN` / `LEN` HIGH and never uses them for thermal reset yet
- `tests/test_motors.py` — current expectations for BTS7960 enable pin initialization and stop behavior
- `.planning/phases/01-core-drive/01-CONTEXT.md` — earlier Phase 1 context that assumed SSR-based thermal reset; superseded for this specific Phase 3 brushed+BTS path

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BTS7960MotorDriver` in `biba-controller/motors/driver.py`: already owns `REN` / `LEN` and is the natural place to add an explicit enable-reset primitive
- `DifferentialDrive` in `biba-controller/motors/driver.py`: existing output gate where PWM can remain forced to zero until recovery completes
- `tests/test_motors.py`: existing BTS7960 tests provide a small, local validation surface for enable-line behavior changes

### Established Patterns
- BTS7960 control is already abstracted behind a dedicated driver class rather than scattered through control flow
- Repository docs consistently describe `RPWM` / `LPWM` plus `REN` / `LEN`, so planning should preserve that naming even if the datasheet names the chip pin `INH`
- Prior Phase 1 context assumed `EN` stays HIGH after boot; Phase 3 planning must treat that as revisitable for the brushed+BTS thermal path

### Integration Points
- Arm/disarm initialization for the brushed BTS7960 runtime
- Any future RP2040 or STM32 HAL layer that owns motor-enable pins directly
- Fault handling path if a thermal latch persists after the enable-reset attempt

</code_context>

<specifics>
## Specific Ideas

- Datasheet evidence locked the behavior:
  overtemperature shutdown is latched, reset requires `INH LOW`, and the minimum reset pulse is 3 us.
- The chosen implementation bias is to use a wider 100 us pulse rather than trying to hit the datasheet floor.
- The SSR is explicitly not required just to clear a thermal latch on the brushed BTS7960 path.
- Repetitive use of overtemperature protection may reduce device lifetime, so reset is a recovery path, not a substitute for fixing heat sinking.

</specifics>

<deferred>
## Deferred Ideas

- Fallback behavior if the BTS7960 still does not recover after the enable-reset pulse: retry policy, permanent fault latch, or explicit operator feedback
- Whether to log a dedicated thermal-latch recovery event for field validation runs
- Whether non-brushed or non-BTS variants should keep SSR-based power cutting for unrelated reasons

</deferred>

---

*Phase: 3-Field Ready*
*Context gathered: 2026-05-16*