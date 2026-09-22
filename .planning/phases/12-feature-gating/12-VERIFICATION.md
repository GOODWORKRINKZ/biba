# Phase 12: Signal Chain Feature Gating — Plan Verification Report

**Verified:** 2026-05-27
**Verifier:** gsd-plan-checker (goal-backward analysis)
**Phase:** 12 — Signal Chain Feature Gating
**Plans checked:** 3 (12-01, 12-02, 12-03)
**Overall verdict:** **NEEDS REVISION** (1 blocker, 3 warnings)

---

## 1. Goal-Backward Trace Matrix

| Success Criterion | Plan(s) | Task(s) | What Delivers It | Confidence |
|-------------------|---------|---------|------------------|------------|
| **FEAT-01**: Each of 17 features has `BIBA_FEATURE_<NAME>` toggle in `biba_config.h` | 12-01 | Task 1 (Step 2) | 17 feature sections with `#ifndef BIBA_FEATURE_<NAME>` / `#define` pattern, all default=1 except REVERSE_PIP=0 per D-07 | **HIGH** — exhaustive enumeration of all 17 toggles in action, each with section template |
| **FEAT-02**: `BIBA_FEATURE_RPM_CLOSED_LOOP=0` ≡ old `BIBA_OPEN_LOOP` | 12-01, 12-02 | 12-01 Task 1 (Step 5); 12-02 Tasks 1-3 | Backward compat `#ifdef BIBA_OPEN_LOOP` → `#define BIBA_FEATURE_RPM_CLOSED_LOOP 0` + `#warning`; all old `#ifndef BIBA_OPEN_LOOP` replaced with cascaded `#if BIBA_FEATURE_*` gates; equivalence table in RESEARCH.md §12.2 | **HIGH** — RESEARCH.md documents exact 1:1 mapping of all old guard behaviors to new |
| **FEAT-03**: `biba_config.h` reorganized with feature-scoped sections | 12-01 | Task 1 (Steps 1-3) | 31 labeled sections: critical safety (no toggles) → 17 feature sections (toggle+params) → non-feature config → `#error` checks | **HIGH** — complete section ordering per RESEARCH.md §5.1, each with `/* --- Feature: ... --- */` header |
| **FEAT-04**: Dependency violations caught by `#error` at compile time | 12-01 | Task 1 (Step 4), Task 3 (Tests 3/3b/3c) | 4 `#error` checks: PI→DR, DUAL_WINDOW→SPECTRAL, LOAD_GATE→SPECTRAL, ANTI_STALL→SPECTRAL. All gated inside `#if BIBA_FEATURE_RPM_CLOSED_LOOP`. Build tests verify violation triggers and corrected cases | **HIGH** — explicit `#error` messages, build tests prove both failure (violation) and success (corrected) paths |
| **FEAT-05**: All existing tests pass with all toggles=1 | 12-02, 12-03 | 12-03 Task 1 (unit tests), 12-03 Task 3 (human smoke) | `pio test -e native_test`, default firmware build, symbol check (no undefined refs), human smoke test with all features enabled | **MEDIUM** — unit test gate is strong; human smoke test is a checkpoint (manual). No automated integration/E2E test for full signal chain. |
| **FEAT-06**: Build with `RPM_CLOSED_LOOP=0` compiles and robot drives in open-loop | 12-03 | Task 2 (open-loop build), Task 3 (open-loop smoke) | `pio run --build-flags="-DBIBA_FEATURE_RPM_CLOSED_LOOP=0"` + human smoke test verifying: arming works, throttle responds, steering responds, failsafe stops motors | **MEDIUM** — build verification is automated; human smoke test is a checkpoint. Truth relies on physical test execution. |

---

## 2. Gap Analysis — Success Criterion Coverage

### 2.1 Requirement Coverage Matrix

| Requirement | 12-01 | 12-02 | 12-03 | Status |
|-------------|:-----:|:-----:|:-----:|--------|
| FEAT-01 (17 toggles in biba_config.h) | ✓ T1 | — | — | **COVERED** |
| FEAT-02 (RPM_CLOSED_LOOP=0 ≡ old OPEN_LOOP) | ✓ T1 | ✓ T1-3 | — | **COVERED** |
| FEAT-03 (biba_config.h reorganized) | ✓ T1 | — | — | **COVERED** |
| FEAT-04 (#error dependency checks) | ✓ T1, T3 | — | — | **COVERED** |
| FEAT-05 (all tests pass, toggles=1) | — | ✓ (declared) | ✓ T1, T3 | **COVERED** |
| FEAT-06 (open-loop build + robot drives) | — | — | ✓ T2, T3 | **COVERED** |

**Result: ✅ All 6 success criteria have covering tasks.** No orphaned requirements.

### 2.2 No Missing Requirements

All 6 FEAT-XX IDs from ROADMAP.md appear in at least one plan's `requirements` frontmatter. The ROADMAP.md also correctly lists FEAT-01 through FEAT-06 under Phase 12.

---

## 3. Dependency Graph Validation

```
Wave 1: [12-01]                    (depends_on: [])
Wave 2: [12-02]                    (depends_on: [01])
Wave 3: [12-03]                    (depends_on: [01, 02])
```

| Check | Result |
|-------|--------|
| All referenced dependencies exist | ✅ 01, 02 both exist in phase directory |
| No circular dependencies | ✅ DAG: 01 → 02 → 03 |
| No forward references | ✅ 02 depends on 01 (past), 03 depends on 01+02 (past) |
| Wave numbers consistent | ✅ Wave 1: depends_on=[], Wave 2: max(deps)+1=2, Wave 3: max(deps)+1=3 |
| 12-02 needs biba_config.h from 12-01 | ✅ Dependency ensures toggle definitions exist before gate injection |
| 12-03 needs both 01 and 02 | ✅ Dependency ensures config + gates are in place before verification |

**Result: ✅ Dependency graph is valid, acyclic, and correctly ordered.**

---

## 4. File Conflict Risk Assessment

| File | 12-01 | 12-02 | 12-03 | Risk |
|------|:-----:|:-----:|:-----:|------|
| `firmware/include/biba_config.h` | ✏️ full rewrite | — | (listed, but verification-only) | **LOW** — 12-02 doesn't touch it; 12-03 only lists it as "files_modified" but tasks are verification-only (build flags, not edits) |
| `firmware/src/modes/mode_standalone.c` | — | ✏️ heavy edits | (listed, verification-only) | **LOW** — 12-01 doesn't touch it; one file, one wave |
| `firmware/targets/RPICO_RP2040/target_config.h` | ✏️ minor (REVERSE_PIP default) | — | (listed) | **LOW** — only 12-01 modifies it |
| `firmware/src/app/zc_detector.h` | ✏️ #ifndef guards | — | — | **LOW** — one wave |
| `firmware/src/app/rpm_spectral_estimator.h` | ✏️ #ifndef guards | — | — | **LOW** — one wave |
| `firmware/src/app/rpm_pi.h` | ✏️ #ifndef guards | — | — | **LOW** — one wave |

**Result: ✅ No same-line conflict risks.** Each file is modified by exactly one wave.

**Note:** 12-03's `files_modified` frontmatter lists `biba_config.h`, `mode_standalone.c`, and `target_config.h`, but its tasks are purely verification (build commands + human checkpoint). If tests fail and fixes are needed, executor will need to loop back to the appropriate wave's plan. This is acceptable — the frontmatter signals which files may need attention during verification, not that they will be modified.

---

## 5. Risk Assessment — What Could Still Fail

### 5.1 Technical Risks

| Risk | Severity | Mitigation in Plans | Residual |
|------|----------|---------------------|----------|
| **Include-order race**: Module `.h` constants defined after `biba_config.h` `#ifndef` defaults take precedence | MEDIUM | 12-01 Task 2 adds `#ifndef` guards to module `.h` files. `mode_standalone.c` line 14 includes `biba_config.h` first | **LOW** — double-guard pattern is robust. If include order changes in future, values are preserved. |
| **`#if` vs `#ifdef` confusion**: Using `#ifdef BIBA_FEATURE_X` when toggle is always defined (as 0 or 1) | HIGH | RESEARCH.md Pitfall 2 explicitly warns; plans consistently use `#if BIBA_FEATURE_<NAME>` (value check) | **MEDIUM** — executor must follow the pattern exactly. One `#ifdef` slip makes a toggle always "on" for preprocessor purposes. Count of `#if` vs `#ifdef` in mode_standalone.c should be verified in 12-03 verify block. |
| **Open-loop equivalence regression**: `BIBA_FEATURE_RPM_CLOSED_LOOP=0` produces different duty than old `BIBA_OPEN_LOOP` | MEDIUM | RESEARCH.md §12.2 documents equivalence; 12-03 Task 3 smoke test verifies physically | **LOW-MEDIUM** — equivalence is proven structurally (same code paths gated), but `biba_mix_differential()` fallback (vs old inlined L∞ ball) introduces a different clipping strategy. This is intentional per CONTEXT.md but the old `BIBA_OPEN_LOOP` mode used the inlined L∞ ball code too — the plan correctly replaces the inlined code with `biba_mix_differential()` only when `MIXER_PROJECTION=0`, which is NOT the same as `RPM_CLOSED_LOOP=0`. The mixer behavior is independent of RPM mode. Verify: with `RPM_CLOSED_LOOP=0` and `MIXER_PROJECTION=1` (default), does the mixer use L∞ ball? Yes — because `MIXER_PROJECTION` gate is independent of `RPM_CLOSED_LOOP`. This is **correct** — open-loop just means no PI, not no L∞ projection. |
| **Blackbox `pi_integral` field**: References `s_rpm_pi_left.integral` which exists even when RPM_PI=0 (variable declarations not gated) | LOW | 12-02 Task 3 gates the field write with `#else → 0` | **LOW** — safe because struct members exist (just zero-valued) |
| **`biba_mix_differential()` correctness**: Function exists but was never called before | MEDIUM | 12-02 Task 2 B4 verifies MIXER_PROJECTION_OFF build compiles; 12-03 Task 2 Build 5 tests this combination | **MEDIUM** — compiles ≠ works correctly. The function does `biba_clamp_unit(throttle ± steer)` which hard-clips instead of proportionally projecting. Per CONTEXT.md this is intended behavior difference. Smoke test will catch gross errors. |
| **Melody=0 motor drive gate**: When MELODY=0, `s_player.active` is always false, so `if (!s_player.active)` always true → motors always driven | LOW | 12-02 Task 2 B9 explicitly documents this behavior; 12-03 Task 2 Build 1 verifies compilation | **LOW** — well-understood behavior, correct by design |
| **`CURRENT_LIMITER=0` safety**: No overcurrent protection | HIGH | `#warning` emitted per 12-01 Task 1 Step 7; documented in RESEARCH.md Risk 3 | **MEDIUM** — warning is compile-time only. Operator must read build output. No runtime safeguard. Acceptable per CONTEXT.md D-05 (limiter IS toggleable). |

### 5.2 Process Risks

| Risk | Severity | Mitigation | Residual |
|------|----------|------------|----------|
| **Human smoke test not performed**: 12-03 Task 3 is a `checkpoint:human-verify` — if skipped, FEAT-05 and FEAT-06 are unverified | HIGH | Gate is `blocking` — executor cannot proceed without human approval | **MEDIUM** — depends on human availability and diligence. The `how-to-verify` section is detailed and actionable. |
| **88-test baseline from Phase 11**: FEAT-05 success criterion references "≥88 tests" but Phase 11 completion report may not exist or count may differ | LOW | 12-03 Task 1 Step 2 checks test count; executor can baseline from current `pio test` output before Phase 12 changes | **LOW** — baseline can be established at execution time |
| **Constant value migration errors**: Executor copies wrong values from module `.h` files | MEDIUM | 12-01 Task 1 CONSTANT MIGRATION NOTES explicitly says "READ the actual numeric values from source" and lists exact files+lines | **MEDIUM** — human executor must read 5 different source files for values. Error-prone. BUT: `#ifndef` guards in module `.h` files mean incorrect biba_config.h values would be silently overridden by module defaults → bug would be hidden, not caught. |

### 5.3 Edge Cases Not Explicitly Covered

| Edge Case | Status | Assessment |
|-----------|--------|------------|
| What happens when `BIBA_FEATURE_RPM_CLOSED_LOOP=0` but individual sub-toggles are still 1? | Covered | Dependency `#error` checks are gated by `#if BIBA_FEATURE_RPM_CLOSED_LOOP` — when master is off, no dependency errors fire. Individual sub-toggles are ignored at call sites because every RPM gate uses `#if BIBA_FEATURE_RPM_CLOSED_LOOP && BIBA_FEATURE_RPM_*`. This is correct per D-02. |
| What happens when `BIBA_FEATURE_RPM_PI=0` but `BIBA_FEATURE_RPM_DR=1`? | Covered | Dependency `#error` catches this: PI requires DR. But the inverse (DR=0, PI=1) is what's tested. The `#error` only fires for PI→DR violation. **Gap: DR=1, PI=0 is allowed (DR runs standalone). Is this intentional?** Research says yes — DR can feed telemetry even without PI. |
| Telemetry printf references gated variables | Covered | 12-02 Task 3 Part B decides NOT to gate DRIVE_DATA printf because variable declarations are not gated → all referenced symbols exist, just with zero values. Reasonable. |
| `BIBA_FEATURE_RPM_RAMP=0` but `RPM_CLOSED_LOOP=1`: what drives the motors? | Covered | 12-02 Task 2 B6 gates ramp in tick. When ramp=0 but RPM_CLOSED_LOOP=1, the ramp block is skipped, `left_out/right_out` retain their values from the mixer (set earlier in tick). PI duty assignment (B7) overrides these when PI=1. When PI=1 and RAMP=0, PI directly sets duty. When PI=0, ramp block skip is irrelevant. **Behavior is correct.** |

---

## 6. Threat Model Completeness

Plan 12-03 includes a threat model with STRIDE analysis and ASVS L1 controls:

| Threat | Coverage | Assessment |
|--------|----------|------------|
| T-12-11: Open-loop firmware uncontrollable (DoS) | Mitigated by human smoke test | ✅ Reasonable — physical test is the only definitive verification |
| T-12-12: Default firmware regression (EoP) | Mitigated by unit tests + smoke test | ✅ Adequate |
| T-12-13: Serial debug leakage (Info Disclosure) | Accepted | ✅ Reasonable — debug only, not production |

**Missing from threat model:**

| Gap | Severity | Description |
|-----|----------|-------------|
| `#error` misconfiguration causing bricked build | LOW | If a developer sets conflicting toggles, the `#error` prevents compilation — this is the intended behavior, not a threat. Recovery: fix toggle values and rebuild. |
| `#warning` fatigue causing operators to ignore warnings | LOW | Multiple `#warning`s (CURRENT_LIMITER, BIBA_OPEN_LOOP deprecation) may cause warning fatigue. Mitigation: only 2 warning sources, both important. Acceptable. |
| Target override silently ignored due to include-order bug | LOW | RESEARCH.md Risk 6 documents this. Mitigation: `target_config.h` included at line 21, before all defaults. Verified by code reading. |

**Result: Threat model is adequate for a compile-time configuration phase.** The main threats (wrong firmware behavior, safety regression) are covered. No STRIDE category is critically missing.

---

## 7. Dimension-by-Dimension Summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| 1. Requirement Coverage | ✅ PASS | All 6 FEAT-XX covered by tasks across 3 plans |
| 2. Task Completeness | ✅ PASS | All tasks have Files + Action + Verify + Done. 12-03 Task 3 is `checkpoint:human-verify` (valid type, no automated verify by design) |
| 3. Dependency Correctness | ✅ PASS | Acyclic DAG: 01 → 02 → 03. Wave numbers consistent. |
| 4. Key Links Planned | ✅ PASS | All artifacts wired: config→gates→build→flash. `biba_mix_differential()` fallback wired in 12-02 Task 2 B4. |
| 5. Scope Sanity | ✅ PASS | 3 tasks/plan, ≤5 files/plan. Well within budget. Total ~9 tasks across 3 plans is healthy. |
| 6. Verification Derivation | ⚠️ WARNING | Some truths in 12-01 and 12-02 are implementation-focused ("BIBA_REVERSE_PIP_ENABLED переименован", "biba_config.h содержит секции-комментарии вида"). Mitigating factor: config/compile-time phases naturally have implementation-level truths. The behavioral truths ("Каждая фича отключается одним define", "нарушения ловятся #error") are correctly user-observable. |
| 7. Context Compliance | ✅ PASS | All 7 locked decisions (D-01 through D-07) have implementing tasks. No deferred ideas present in plans. Discretion areas correctly left to planner. |
| 7b. Scope Reduction | ✅ PASS | No scope reduction language found. All decisions delivered fully. DUAL_WINDOW "no params yet — placeholder" is accurate (feature has toggle but no configurable params beyond hint_hz state variables). |
| 7c. Architectural Tier | ✅ PASS | All tasks place code in correct tiers per Architectural Responsibility Map. Firmware config in biba_config.h, call-site gates in mode_standalone.c (App tier), no security-sensitive logic placed in less-trusted tiers. |
| 8. Nyquist Compliance | ⏭️ SKIPPED | RESEARCH.md has no "Validation Architecture" section → nyquist validation not applicable per skip condition. |
| 9. Cross-Plan Data Contracts | ✅ PASS | No conflicting transforms. Plan 01 produces toggle definitions; Plan 02 consumes via `#if`. Plan 03 consumes built artifacts. No shared data streams with incompatible transformations. |
| 10. copilot-instructions.md | ⏭️ SKIPPED | No `copilot-instructions.md` in workspace root. |
| 11. Research Resolution | ❌ BLOCKER | RESEARCH.md §16 "Open Questions" section has 3 questions with recommendations but is NOT marked `(RESOLVED)`. Individual questions lack inline `RESOLVED` markers. See Issue 1 below. |
| 12. Pattern Compliance | ⏭️ SKIPPED | No PATTERNS.md for this phase. |

---

## 8. Detailed Issues

### Blockers (must fix before execution)

**1. [research_resolution] RESEARCH.md has unresolved open questions**

- **Plan:** phase-level (RESEARCH.md)
- **Severity:** BLOCKER
- **Description:** RESEARCH.md `## 16. Open Questions` section (lines 607-626) lists 3 questions with recommendations but the section heading is not suffixed with `(RESOLVED)` and individual questions lack inline `RESOLVED` markers:
  1. "Should ZC detector parameters move to biba_config.h?" — Recommended: YES. Plan 12-01 already implements this.
  2. "Should heading-hold PID gains move to biba_config.h?" — Recommended: YES. Plan 12-01 already implements this (as `BIBA_HEADING_KP` etc.).
  3. "Should state variables be `#if`-gated for RAM savings?" — Recommended: Gate RPM_PI and HEADING_HOLD. Plan 12-02 explicitly decides NOT to gate variable declarations, which is a valid resolution but differs from the recommendation.
- **Fix:** Either:
  - (a) Rename section to `## 16. Open Questions (RESOLVED)` and add `RESOLVED: <decision>` after each question, OR
  - (b) For question 3: explicitly state "RESOLVED: Do NOT gate variable declarations in Phase 12 — keep all state variables unconditionally declared to avoid complexity in blackbox/telemetry references. Revisit in follow-up phase if RAM pressure warrants."
  - This is a ~2-line fix to RESEARCH.md.

### Warnings (should fix — execution can proceed)

**2. [verification_derivation] Implementation-focused truths in plan frontmatter**

- **Plan:** 12-01, 12-02
- **Severity:** WARNING
- **Description:** Several `must_haves.truths` describe implementation details rather than user-observable outcomes:
  - 12-01: "BIBA_REVERSE_PIP_ENABLED переименован в BIBA_FEATURE_REVERSE_PIP" — this is a rename, not a user-observable truth
  - 12-01: "biba_config.h содержит секции-комментарии вида /* --- Feature: ... */" — file structure, not behavior
  - 12-02: "Каждая фича в mode_standalone.c защищена #if BIBA_FEATURE_<NAME> на месте вызова" — implementation pattern
  - 12-02: "Старый #ifndef BIBA_OPEN_LOOP / #ifdef BIBA_OPEN_LOOP полностью заменён" — code cleanup
- **Mitigating factor:** This is a compile-time configuration phase where implementation truths ARE the deliverable. The behavioral truths (e.g., "BIBA_FEATURE_RPM_CLOSED_LOOP=0 производит поведение, идентичное старому BIBA_OPEN_LOOP") are correctly framed. No action required, but noted for future phases.
- **Fix:** Consider reframing as: "Developer can disable any feature with one `#define` change" (behavioral) instead of "Каждая фича имеет тумблер" (structural).

**3. [scope_sanity] 12-03 files_modified frontmatter is aspirational**

- **Plan:** 12-03
- **Severity:** WARNING
- **Description:** 12-03's frontmatter lists `files_modified: firmware/include/biba_config.h, firmware/src/modes/mode_standalone.c, firmware/targets/RPICO_RP2040/target_config.h` but all three tasks are verification-only (build commands, unit tests, human checkpoint). No source files are actually edited in this plan. If tests fail, fixes would loop back to 12-01 or 12-02.
- **Fix:** Either remove `files_modified` (if truly verification-only) or add a note: "files_modified: (none — verification only; failures loop back to Waves 1-2)".

**4. [risk] Constant value migration is error-prone (human factor)**

- **Plan:** 12-01, Task 1
- **Severity:** WARNING
- **Description:** Task 1 requires the executor to read exact numeric values from 5 different source files (zc_detector.h, rpm_spectral_estimator.h, rpm_pi.h, mode_standalone.c lines 85-88, mode_standalone.c lines 200-203 and 213-215). A single typo in a constant value would be silently overridden by the `#ifndef` guard in the module `.h` file, making the bug invisible at compile time and hard to detect at runtime.
- **Mitigating factor:** The `#ifndef` guards ensure module defaults win if biba_config.h has wrong values → robot behavior doesn't change, but the "single source of truth" goal is undermined.
- **Fix:** Consider adding a post-migration verification step: `diff <(grep '#define BIBA_RPM_PI_KP' firmware/include/biba_config.h) <(grep '#define BIBA_RPM_PI_KP' firmware/src/app/rpm_pi.h)` to confirm values match. Add to 12-01 Task 1 `<verify>` block.

---

## 9. Structured Issues (YAML)

```yaml
issues:
  - plan: null  # phase-level
    dimension: research_resolution
    severity: blocker
    description: "RESEARCH.md has '## 16. Open Questions' section without '(RESOLVED)' suffix and individual questions lack inline RESOLVED markers. 3 questions have recommendations but are not formally resolved."
    fix_hint: "Rename section to '## 16. Open Questions (RESOLVED)' and add 'RESOLVED: <decision>' after each question. For Q3 (state variable gating), explicitly state: 'RESOLVED: Do NOT gate variable declarations in Phase 12 — unconditional declarations avoid complexity in blackbox/telemetry references. Revisit if RAM pressure warrants.'"

  - plan: "12-01"
    dimension: verification_derivation
    severity: warning
    description: "Some must_haves.truths are implementation-focused: 'BIBA_REVERSE_PIP_ENABLED переименован', 'biba_config.h содержит секции-комментарии вида...'. For a config phase this is partially expected but reduces verifiability."
    fix_hint: "Reframe as behavioral truths where possible, e.g., 'Developer can locate any feature toggle by scanning comment headers' instead of 'содержит секции-комментарии'."

  - plan: "12-02"
    dimension: verification_derivation
    severity: warning
    description: "Some must_haves.truths are implementation-focused: 'Каждая фича защищена #if...', 'Старый #ifndef BIBA_OPEN_LOOP полностью заменён'. These describe code structure, not observable behavior."
    fix_hint: "Reframe as behavioral truths, e.g., 'When BIBA_FEATURE_X=0, the X feature code path is never executed (zero CPU cost, zero side effects)'."

  - plan: "12-03"
    dimension: scope_sanity
    severity: warning
    description: "files_modified lists 3 files but all tasks are verification-only. No source edits in this plan. If tests fail, executor needs to loop back to Waves 1-2."
    fix_hint: "Either remove files_modified or add note: '(verification only — failures loop back to 12-01 or 12-02)'."

  - plan: "12-01"
    dimension: risk
    severity: warning
    description: "Task 1 requires copying ~30 numeric constants from 5 source files. A typo would be silently hidden by #ifndef guards in module .h files. No post-migration value comparison step."
    task: 1
    fix_hint: "Add to Task 1 <verify> block: diff-based comparison of each moved constant between biba_config.h and its original module .h file."
```

---

## 10. Recommendation

**1 BLOCKER** requires resolution before execution:

> **Fix RESEARCH.md §16:** Mark the "Open Questions" section as `(RESOLVED)` and add explicit resolution statements for each of the 3 questions. This is a ~2-line documentation fix — the plans already implement the recommended answers. Estimated fix time: 2 minutes.

**3 WARNINGS** are non-blocking quality improvements:
- Implementation-focused truths in frontmatter (cosmetic, no behavioral impact)
- 12-03 files_modified aspirational listing (documentation clarity)
- Missing constant value verification step (risk mitigation, not correctness)

**After blocker is resolved:** Re-run `/gsd-plan-phase 12` plan checker for final PASS, then proceed to `/gsd-execute-phase 12`.

---

## 11. Plan Quality Assessment

| Quality Attribute | Rating | Notes |
|-------------------|--------|-------|
| **Specificity** | ⭐⭐⭐⭐⭐ | Every task has concrete code snippets, exact line numbers, and explicit `#if` patterns. Executor can follow without guessing. |
| **Completeness** | ⭐⭐⭐⭐ | All 17 toggles enumerated. All call sites mapped (ISR, init, tick, blackbox). Edge cases addressed (telemetry printf, melody motor gate, DRIVE_DATA). One gap: no post-migration constant-value verification. |
| **Testability** | ⭐⭐⭐⭐ | 12-01 Task 3: 5 build tests including dependency violation triggers. 12-03 Task 2: 7 off-combination builds. Human smoke test is detailed. Missing: automated integration test for full signal chain. |
| **Research Foundation** | ⭐⭐⭐⭐⭐ | RESEARCH.md is comprehensive: codebase map, exact line numbers, include-order analysis, pitfall catalog, equivalence proof for old→new migration, architectural responsibility map. |
| **Risk Awareness** | ⭐⭐⭐⭐ | Threat model covers key risks. RESEARCH.md §13 lists 6 risk areas with mitigations. Missing: explicit risk around constant value migration typos. |

**Overall:** Plans are well-researched, specific, and executable. The single blocker is a documentation formality. Once resolved, plans are ready for execution with high confidence of success.

---

*Verification performed by gsd-plan-checker (goal-backward analysis). Revision gate: max 3 iterations. Current iteration: 1.*
