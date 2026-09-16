#!/usr/bin/env python
"""
Configure a fresh ODrive v3.6-56V (fw 0.5.6) for the BiBa UART-ASCII link.

Two phases:

  * config   (default) — write motor/encoder/controller + UART-A settings
                         and save to NVM. No motor motion.
  * calibrate          — run FULL_CALIBRATION_SEQUENCE (motor + Hall polarity
                         + encoder offset) on each axis. MOTORS SPIN — make
                         sure the wheels are free to rotate.

Usage:
    .venv/bin/python scripts/odrive_setup_uart.py            # config + save
    .venv/bin/python scripts/odrive_setup_uart.py --calibrate

Values mirror the notes in docs (see memory: odrive-fw-056-upgrade,
odrive-rp2040-failure-modes, odrive-ascii-tuning):

  * requested_current_range = 60          (0.5.6 default; 30 breaks current sense)
  * dc_max_negative_current = -30         (else DC_BUS_OVER_REGEN on calib spin-down)
  * current_lim = 30 A                    (100 → current-sense saturation / hang)
  * encoder bandwidth = 100               (1000 → noisy Hall vel → overspeed cascade)
  * vel_gain = 0.2, vel_integrator_gain = 0.15
  * vel_limit = 10 rev/s
  * Hall encoder: mode=1, cpr=90, pole_pairs=15
  * UART-A: enable_uart_a=1, uart_a_baudrate=115200, ASCII protocol (uart0_protocol=3)
"""
import sys
import time

import odrive

# ---- target values ------------------------------------------------------
CURRENT_LIM_A = 30.0
REQUESTED_CURRENT_RANGE = 60.0
TORQUE_CONSTANT = 0.04
POLE_PAIRS = 15

ENC_MODE_HALL = 1
ENC_CPR = 90
ENC_BANDWIDTH = 100.0

CONTROL_MODE_VELOCITY = 2
INPUT_MODE_PASSTHROUGH = 1
VEL_GAIN = 0.2
VEL_INTEGRATOR_GAIN = 0.15
VEL_LIMIT = 10.0

DC_MAX_NEGATIVE_CURRENT = -30.0

UART_BAUDRATE = 115200
UART_PROTOCOL_ASCII = 3


def configure_axis(ax, name):
    print(f"--- {name} ---")
    ax.motor.config.pole_pairs = POLE_PAIRS
    ax.motor.config.current_lim = CURRENT_LIM_A
    ax.motor.config.requested_current_range = REQUESTED_CURRENT_RANGE
    ax.motor.config.torque_constant = TORQUE_CONSTANT

    ax.encoder.config.mode = ENC_MODE_HALL
    ax.encoder.config.cpr = ENC_CPR
    ax.encoder.config.bandwidth = ENC_BANDWIDTH

    ax.controller.config.control_mode = CONTROL_MODE_VELOCITY
    ax.controller.config.input_mode = INPUT_MODE_PASSTHROUGH
    ax.controller.config.vel_gain = VEL_GAIN
    ax.controller.config.vel_integrator_gain = VEL_INTEGRATOR_GAIN
    ax.controller.config.vel_limit = VEL_LIMIT

    print(f"  pole_pairs={ax.motor.config.pole_pairs} current_lim={ax.motor.config.current_lim} "
          f"req_range={ax.motor.config.requested_current_range} torque_const={ax.motor.config.torque_constant}")
    print(f"  enc mode={ax.encoder.config.mode} cpr={ax.encoder.config.cpr} "
          f"bandwidth={ax.encoder.config.bandwidth}")
    print(f"  control_mode={ax.controller.config.control_mode} input_mode={ax.controller.config.input_mode} "
          f"vel_gain={ax.controller.config.vel_gain} vel_int_gain={ax.controller.config.vel_integrator_gain} "
          f"vel_limit={ax.controller.config.vel_limit}")


def configure_global(od):
    od.config.dc_max_negative_current = DC_MAX_NEGATIVE_CURRENT
    od.config.enable_uart_a = True
    od.config.uart_a_baudrate = UART_BAUDRATE
    od.config.uart0_protocol = UART_PROTOCOL_ASCII
    print(f"dc_max_negative_current={od.config.dc_max_negative_current}")
    print(f"enable_uart_a={od.config.enable_uart_a} "
          f"uart_a_baudrate={od.config.uart_a_baudrate} "
          f"uart0_protocol={od.config.uart0_protocol}")


def calibrate_axis(od, ax, name):
    print(f"=== {name}: FULL_CALIBRATION_SEQUENCE (motor spins ~17s) ===")
    # Clear latched global errors first — they block arming (see memory
    # odrive-fw-056-upgrade: "clear_errors before every calibration run").
    try:
        od.clear_errors()
    except Exception as ex:
        print(f"  (clear_errors: {type(ex).__name__}: {ex})")

    ax.requested_state = 3  # AXIS_STATE_FULL_CALIBRATION_SEQUENCE
    # Poll until calibration completes or errors.
    deadline = time.time() + 40
    while time.time() < deadline:
        time.sleep(0.5)
        print(f"  {name} state={ax.current_state} motor_error={ax.motor.error} "
              f"encoder_error={ax.encoder.error}")
        if ax.current_state == 1:  # IDLE
            break
    if ax.motor.error != 0 or ax.encoder.error != 0:
        print(f"  !! {name} calibration ended with errors: "
              f"motor={hex(ax.motor.error)} encoder={hex(ax.encoder.error)}")
        return False

    # CRITICAL: persist the pre_calibrated flags *now*, while the runtime
    # state is ready (is_ready=True / is_calibrated=True).  The setter has a
    # guard (check_pre_calibrated) that silently resets the flag to False if
    # the encoder/motor is NOT ready — so setting it after a reboot fails.
    print(f"  {name} after calib: motor.is_calibrated={ax.motor.is_calibrated} "
          f"encoder.is_ready={ax.encoder.is_ready}")
    ax.encoder.config.pre_calibrated = True
    ax.motor.config.pre_calibrated = True
    print(f"  {name} set flags: encoder.pre_calibrated={ax.encoder.config.pre_calibrated} "
          f"motor.pre_calibrated={ax.motor.config.pre_calibrated}")
    return (ax.encoder.config.pre_calibrated and ax.motor.config.pre_calibrated)


def main():
    calib = "--calibrate" in sys.argv

    od = odrive.find_any(timeout=10)
    print(f"ODrive {od.serial_number} fw {od.fw_version_major}.{od.fw_version_minor}.{od.fw_version_revision}")

    if not calib:
        print("=== Phase 1: config (no motion) ===")
        configure_global(od)
        configure_axis(od.axis0, "axis0 (LEFT)")
        configure_axis(od.axis1, "axis1 (RIGHT)")

        print("=== Saving config (NVM) ===")
        try:
            od.save_configuration()
            print("save_configuration() returned (ObjectLostError is benign)")
        except Exception as ex:
            print(f"save_configuration() raised {type(ex).__name__}: {ex} — saved anyway (benign)")
        print("=== Done. Run with --calibrate to do Hall calibration (motors spin). ===")
        return 0

    print("=== Phase 2: Hall calibration (MOTORS SPIN — wheels must be free) ===")
    ok0 = calibrate_axis(od, od.axis0, "axis0 (LEFT)")
    ok1 = calibrate_axis(od, od.axis1, "axis1 (RIGHT)")

    if ok0 and ok1:
        print("=== Saving calibrated flags + offsets to NVM ===")
        try:
            od.save_configuration()
        except Exception as ex:
            print(f"save_configuration() raised {type(ex).__name__}: {ex} — saved anyway (benign)")

        print("=== Rebooting to verify persistence ===")
        try:
            od.reboot()
        except Exception as ex:
            print(f"  (reboot raised {type(ex).__name__}: {ex})")
        time.sleep(3)
        od = odrive.find_any(timeout=20)
        print("=== Verify after reboot ===")
        ok = True
        for name, ax in (("axis0", od.axis0), ("axis1", od.axis1)):
            e = ax.encoder
            print(f"  {name}: encoder.is_ready={e.is_ready} "
                  f"encoder.pre_calibrated={e.config.pre_calibrated} "
                  f"motor.is_calibrated={ax.motor.is_calibrated} "
                  f"motor.pre_calibrated={ax.motor.config.pre_calibrated}")
            if not (e.is_ready and e.config.pre_calibrated
                    and ax.motor.is_calibrated and ax.motor.config.pre_calibrated):
                ok = False
        if ok:
            print("=== SUCCESS: calibration persisted across reboot. ===")
            return 0
        print("=== WARNING: flags did NOT persist. Re-run calibration. ===")
        return 1
    print("=== Calibration incomplete (see errors above). ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
