"""Main runtime loop for the BiBa wheeled platform controller."""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType
from typing import Optional

import pigpio

import config
from bms.daly import BatteryState, DalyBMS, DalyBMSBle
from bms.poller import BMSPoller
from buzzer.beacon import BeaconManager
from buzzer.melodies import FUN_PLAYLIST
from buzzer.motor_synth import MotorSynth
from crsf.receiver import CRSFReceiver
from crsf.telemetry import CRSFTelemetry
from motors.driver import BTS7960MotorDriver, DifferentialDrive, MotorDriver
from system_stats import SystemStats

LOGGER = logging.getLogger("biba-controller")
RUNNING = True
_BATTERY_TELEMETRY_LOG_INTERVAL_S = 5.0


class _NullDrive:
    def drive(self, throttle: float, steering: float, dt: float = 0.02) -> None:
        del throttle, steering, dt

    def stop(self) -> None:
        pass

    def check_failsafe(self, last_frame_time: float) -> bool:
        del last_frame_time
        return False

    def emergency_stop(self) -> None:
        pass


class _NullBuzzer:
    def off(self) -> None:
        pass

    def startup_tone(self) -> None:
        pass

    def shutdown_tone(self) -> None:
        pass

    def connected_tone(self) -> None:
        pass

    def disconnected_tone(self) -> None:
        pass

    def arm_tone(self) -> None:
        pass

    def disarm_tone(self) -> None:
        pass

    def failsafe_tone(self) -> None:
        pass

    def sos_beacon(self) -> None:
        pass

    def low_voltage_alarm(self) -> None:
        pass

    def play_named(self, name: str) -> None:
        del name

    def play_named_async(self, name: str) -> None:
        del name

    def set_control_active(self, active: bool) -> None:
        del active

    def play_blheli(self, melody_str: str, tempo_bpm: int = 120) -> None:
        del melody_str, tempo_bpm


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    del signum, frame
    global RUNNING
    RUNNING = False


def _is_armed(channels: list[float]) -> bool:
    if len(channels) <= config.CH_ARM:
        return False
    return channels[config.CH_ARM] > config.ARM_THRESHOLD


def _get_channel(channels: list[float], index: int) -> float:
    if index >= len(channels):
        return 0.0
    return channels[index]


def _battery_is_low(state: BatteryState) -> bool:
    if state.cells and state.min_cell > 0:
        return state.min_cell <= config.LOW_CELL_VOLTAGE
    return state.voltage <= config.LOW_PACK_VOLTAGE


def _connect_pigpio(retries: int = 5, delay: float = 1.0) -> pigpio.pi:
    """Try to connect to pigpiod, retrying on failure."""
    for attempt in range(1, retries + 1):
        pi = pigpio.pi()
        if pi.connected:
            return pi
        pi.stop()
        if attempt < retries:
            LOGGER.warning("pigpio attempt %d/%d failed, retrying in %.1fs", attempt, retries, delay)
            time.sleep(delay)
    LOGGER.warning("pigpio: all %d attempts failed", retries)
    return pigpio.pi()


def _create_bms() -> DalyBMS:
    if config.BMS_TRANSPORT == "BLE":
        return DalyBMSBle(
            config.BMS_BLE_ADDRESS,
            config.BMS_BLE_SERVICE_UUID,
            config.BMS_BLE_WRITE_UUID,
            config.BMS_BLE_NOTIFY_UUID,
            config.BMS_BLE_TIMEOUT_S,
        )
    return DalyBMS(config.BMS_PORT, config.BMS_BAUD)


def _create_motor_pair(pi: pigpio.pi) -> tuple[object, object]:
    if config.MOTOR_DRIVER_TYPE == "BTS7960":
        left_motor = BTS7960MotorDriver(
            pi,
            config.LEFT_MOTOR_RPWM,
            config.LEFT_MOTOR_LPWM,
            config.LEFT_MOTOR_REN,
            config.LEFT_MOTOR_LEN,
            inverted=bool(config.MOTOR1_INVERTED),
        )
        right_motor = BTS7960MotorDriver(
            pi,
            config.RIGHT_MOTOR_RPWM,
            config.RIGHT_MOTOR_LPWM,
            config.RIGHT_MOTOR_REN,
            config.RIGHT_MOTOR_LEN,
            inverted=bool(config.MOTOR2_INVERTED),
        )
        return left_motor, right_motor

    left_motor = MotorDriver(
        pi,
        config.MOTOR1_PWM,
        config.MOTOR1_DIR,
        inverted=bool(config.MOTOR1_INVERTED),
    )
    right_motor = MotorDriver(
        pi,
        config.MOTOR2_PWM,
        config.MOTOR2_DIR,
        inverted=bool(config.MOTOR2_INVERTED),
    )
    return left_motor, right_motor


def _send_system_telemetry(telemetry: CRSFTelemetry, stats: SystemStats) -> None:
    telemetry.send_system_stats(
        cpu_pct=stats.cpu_percent(),
        mem_pct=stats.memory_percent(),
    )


def _clamp_battery_current_a(current_a: float) -> float:
    return max(0.0, current_a)


def _encode_crsf_current_da(current_a: float) -> int:
    return max(0, int(round(current_a * 10)))


def _log_battery_telemetry(state: BatteryState, now: float, last_log_at: float) -> float:
    if now - last_log_at < _BATTERY_TELEMETRY_LOG_INTERVAL_S:
        return last_log_at

    clamped_current_a = _clamp_battery_current_a(state.current)
    LOGGER.info(
        (
            "Battery telemetry raw_current_a=%.2f clamped_current_a=%.2f "
            "crsf_current_da=%d voltage_v=%.2f soc_pct=%d"
        ),
        state.current,
        clamped_current_a,
        _encode_crsf_current_da(clamped_current_a),
        state.voltage,
        int(round(state.soc)),
    )
    return now


def _send_battery_telemetry(telemetry: CRSFTelemetry, state: Optional[BatteryState]) -> None:
    if state is None:
        telemetry.send_battery(
            voltage_v=config.TEST_BATTERY_VOLTAGE,
            current_a=config.TEST_BATTERY_CURRENT,
            capacity_mah=config.TEST_BATTERY_CAPACITY_MAH,
            remaining_pct=config.TEST_BATTERY_REMAINING_PCT,
        )
        return

    telemetry.send_battery(
        voltage_v=state.voltage,
        current_a=_clamp_battery_current_a(state.current),
        capacity_mah=0,
        remaining_pct=int(round(state.soc)),
    )


def main() -> int:
    """Run the BiBa control loop until a shutdown signal is received."""
    _setup_logging()

    receiver = CRSFReceiver(config.CRSF_PORT, config.CRSF_BAUD, config.SERIAL_TIMEOUT_S)
    telemetry = CRSFTelemetry(None)
    bms = _create_bms()
    bms_poller: Optional[BMSPoller] = None
    stats = SystemStats()
    pi = _connect_pigpio()
    if pi.connected:
        left_motor, right_motor = _create_motor_pair(pi)
        drive = DifferentialDrive(left_motor, right_motor)
        synth_pwm_pins: list[int] = []
        if config.LEFT_MOTOR_ENABLED:
            synth_pwm_pins.extend([
                config.LEFT_MOTOR_RPWM,
                config.LEFT_MOTOR_LPWM,
            ])
        if config.RIGHT_MOTOR_ENABLED:
            synth_pwm_pins.extend([
                config.RIGHT_MOTOR_RPWM,
                config.RIGHT_MOTOR_LPWM,
            ])
        buzzer = MotorSynth(
            pi,
            synth_pwm_pins,
        )
    else:
        LOGGER.warning("Could not connect to pigpio daemon, starting in telemetry-only mode")
        drive = _NullDrive()
        buzzer = _NullBuzzer()
    beacon = BeaconManager(
        delay_s=config.BEACON_DELAY_S,
        enabled=config.BEACON_ENABLED,
    )

    try:
        receiver.open()
        telemetry.attach(receiver.serial_port)
    except Exception as exc:
        LOGGER.exception("Hardware initialization failed: %s", exc)
        drive.stop()
        buzzer.off()
        if pi.connected:
            pi.stop()
        return 1

    try:
        bms.open()
        bms_poller = BMSPoller(bms, interval_s=config.BMS_POLL_INTERVAL_S)
        bms_poller.start()
    except Exception as exc:
        LOGGER.warning("Daly BMS unavailable on %s: %s", config.BMS_PORT, exc)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    armed = False
    had_connection = False
    low_voltage_active = False
    melody_zone = -1
    last_frame_time = time.monotonic()
    last_telemetry_send = 0.0
    last_battery_telemetry_log = 0.0
    _last_debug_log = 0.0
    loop_period = 1.0 / max(config.MAIN_LOOP_HZ, 1)

    LOGGER.info("BiBa controller started")
    if config.STARTUP_MELODY:
        buzzer.play_named(config.STARTUP_MELODY)
    else:
        buzzer.startup_tone()

    try:
        while RUNNING:
            loop_started_at = time.monotonic()
            received_frame = False

            try:
                channels = receiver.get_channels()
            except Exception as exc:
                LOGGER.warning("Failed to read CRSF channels: %s", exc)
                channels = None

            if channels is not None:
                received_frame = True
                last_frame_time = loop_started_at
                arm_state_changed = False

                if not had_connection:
                    had_connection = True
                    buzzer.connected_tone()
                beacon.on_connected()

                requested_armed = _is_armed(channels)
                if requested_armed != armed:
                    arm_state_changed = True
                    armed = requested_armed
                    if armed:
                        LOGGER.info("Platform armed")
                        buzzer.arm_tone()
                    else:
                        LOGGER.info("Platform disarmed")
                        buzzer.disarm_tone()

                throttle = _get_channel(channels, config.CH_THROTTLE)
                steering = _get_channel(channels, config.CH_STEERING)
                arm_ch = _get_channel(channels, config.CH_ARM)
                control_active = armed and (
                    abs(throttle) > config.MOTOR_DEADBAND or abs(steering) > config.MOTOR_DEADBAND
                )
                buzzer.set_control_active(control_active)
                if loop_started_at - _last_debug_log >= 1.0:
                    _last_debug_log = loop_started_at
                    ch_vals = [f"{v:+.2f}" for v in channels[:6]]
                    LOGGER.info(
                        "CH[%s] thr=%.2f str=%.2f arm_ch=%.2f armed=%s",
                        ",".join(ch_vals), throttle, steering, arm_ch, armed,
                    )
                if armed:
                    drive.drive(throttle, steering, loop_period)
                else:
                    drive.drive(0.0, 0.0, loop_period)

                # Manual beacon toggle via RC channel
                beacon_ch = _get_channel(channels, config.CH_BEACON)
                beacon.set_manual(beacon_ch > config.ARM_THRESHOLD)

                # Melody selection via RC channel
                if config.ENABLE_RC_MELODIES:
                    melody_ch = _get_channel(channels, config.CH_MELODY)
                    num_melodies = len(FUN_PLAYLIST)
                    raw_val = (melody_ch + 1.0) / 2.0  # -1..1 → 0..1
                    new_zone = min(int(raw_val * num_melodies), num_melodies - 1)
                    if melody_zone == -1:
                        melody_zone = new_zone
                    elif new_zone != melody_zone:
                        melody_zone = new_zone
                        if not arm_state_changed:
                            buzzer.play_named_async(FUN_PLAYLIST[melody_zone])

            if not received_frame and drive.check_failsafe(last_frame_time):
                if armed:
                    LOGGER.warning("Failsafe triggered, disarming platform")
                    buzzer.failsafe_tone()
                drive.drive(0.0, 0.0, loop_period)
                if had_connection:
                    had_connection = False
                    buzzer.disconnected_tone()
                armed = False
                beacon.on_failsafe(loop_started_at)

            if beacon.should_sos(loop_started_at):
                buzzer.sos_beacon()

            if loop_started_at - last_telemetry_send >= config.BMS_POLL_INTERVAL_S:
                last_telemetry_send = loop_started_at
                battery_state = bms_poller.latest_state if bms_poller else None

                try:
                    _send_battery_telemetry(telemetry, battery_state)
                    if battery_state is not None:
                        last_battery_telemetry_log = _log_battery_telemetry(
                            battery_state,
                            now=loop_started_at,
                            last_log_at=last_battery_telemetry_log,
                        )
                except Exception as exc:
                    LOGGER.warning("Failed to send CRSF battery telemetry: %s", exc)

                try:
                    _send_system_telemetry(telemetry, stats)
                except Exception as exc:
                    LOGGER.warning("Failed to send CRSF system telemetry: %s", exc)

                if battery_state is not None:
                    is_low_voltage = _battery_is_low(battery_state)
                    if is_low_voltage and not low_voltage_active:
                        low_voltage_active = True
                        LOGGER.warning("Low battery warning: %.2fV", battery_state.voltage)
                        buzzer.low_voltage_alarm()
                    elif not is_low_voltage:
                        low_voltage_active = False
                else:
                    low_voltage_active = False

            elapsed = time.monotonic() - loop_started_at
            if elapsed < loop_period:
                time.sleep(loop_period - elapsed)
    finally:
        LOGGER.info("Shutting down BiBa controller")
        if bms_poller:
            bms_poller.stop()
        drive.emergency_stop()
        buzzer.shutdown_tone()
        buzzer.off()
        receiver.close()
        bms.close()
        if pi.connected:
            pi.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())