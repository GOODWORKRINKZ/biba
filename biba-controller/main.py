"""Main runtime loop for the BiBa wheeled platform controller."""

from __future__ import annotations

import logging
import signal
import time
from pathlib import Path
from types import FrameType
from typing import Optional

import pigpio
import yaml

import config
from bms.daly import BatteryState, DalyBMS, DalyBMSBle
from bms.poller import BMSPoller
from buzzer.beacon import BeaconManager
from buzzer.melodies import FUN_PLAYLIST
from buzzer.motor_synth import MotorSynth
from buzzer.voice_selector import VoiceSelector
from crsf.receiver import CRSFReceiver
from crsf.telemetry import CRSFTelemetry
from motors.current_control import MotorCurrentSample, MotorLimitConfig, MotorLimitResult, apply_motor_limits
from motors.current_sense import MotorCurrentCalibration, NullMotorCurrentReader, open_ads1115_current_reader
from motors.driver import BTS7960MotorDriver, DifferentialDrive, MotorDriver
from motors.ramping import ScalarKalmanFilter
from system_stats import SystemStats

LOGGER = logging.getLogger("biba-controller")
RUNNING = True
_BATTERY_TELEMETRY_LOG_INTERVAL_S = 5.0


class _NullDrive:
    def mix_and_ramp(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
        del throttle, steering, dt
        return (0.0, 0.0)

    def apply_output(
        self,
        left_duty: float,
        right_duty: float,
        *,
        throttle: float = 0.0,
        steering: float = 0.0,
        dt: float = 0.02,
    ) -> tuple[float, float]:
        del left_duty, right_duty, throttle, steering, dt
        return (0.0, 0.0)

    def drive(self, throttle: float, steering: float, dt: float = 0.02) -> tuple[float, float]:
        del throttle, steering, dt
        return (0.0, 0.0)

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

    def play_wav(self, path: str) -> None:
        del path

    def play_spectral(self, path: str) -> None:
        del path


def _play_grouped_voice(
    selector: VoiceSelector,
    event: str,
    voices: list[str],
    buzzer,
) -> bool:
    path = selector.choose(event, voices)
    if path is None:
        return False
    player = getattr(buzzer, "play_spectral", None)
    if player is None:
        player = buzzer.play_wav
    player(path)
    return True


def _create_synth_pins() -> tuple[list[int], list[int]]:
    synth_pwm_pins: list[int] = []
    synth_comp_pins: list[int] = []
    if config.LEFT_MOTOR_ENABLED:
        synth_pwm_pins.append(config.LEFT_MOTOR_RPWM)
        synth_comp_pins.append(config.LEFT_MOTOR_LPWM)
    if config.RIGHT_MOTOR_ENABLED:
        synth_pwm_pins.append(config.RIGHT_MOTOR_RPWM)
        synth_comp_pins.append(config.RIGHT_MOTOR_LPWM)
    return synth_pwm_pins, synth_comp_pins


def _create_buzzer(pi: pigpio.pi):
    synth_pwm_pins, synth_comp_pins = _create_synth_pins()
    return MotorSynth(
        pi,
        synth_pwm_pins,
        comp_pins=synth_comp_pins,
    )


def _load_voice_audition_candidates(path: str) -> list[str]:
    if not path:
        raise ValueError("VOICE_AUDITION_MANIFEST must be set when audition mode is enabled")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list) or not all(isinstance(item, str) and item.strip() for item in candidates):
        raise ValueError("audition manifest candidates must be a non-empty list of strings")
    return [item.strip() for item in candidates]


def _run_voice_audition_mode() -> int:
    pi = _connect_pigpio()
    if not pi.connected:
        LOGGER.warning("Could not connect to pigpio daemon, voice audition mode cannot start")
        return 1

    buzzer = _create_buzzer(pi)
    try:
        for candidate in _load_voice_audition_candidates(config.VOICE_AUDITION_MANIFEST):
            buzzer.play_spectral(candidate)
    finally:
        buzzer.off()
        pi.stop()

    return 0


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


def _create_throttle_filter() -> Optional[ScalarKalmanFilter]:
    if config.THROTTLE_FILTER_MODE != "KALMAN":
        return None
    return ScalarKalmanFilter(
        process_noise=config.THROTTLE_KALMAN_PROCESS_NOISE,
        measurement_noise=config.THROTTLE_KALMAN_MEASUREMENT_NOISE,
    )


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


def _send_system_telemetry(
    telemetry: CRSFTelemetry,
    stats: SystemStats,
    left_current_a: float = 0.0,
    right_current_a: float = 0.0,
) -> None:
    telemetry.send_system_stats(
        cpu_pct=stats.cpu_percent(),
        mem_pct=stats.memory_percent(),
        left_motor_current_a=max(0.0, left_current_a),
        right_motor_current_a=max(0.0, right_current_a),
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
            voltage_v=0.0,
            current_a=0.0,
            capacity_mah=0,
            remaining_pct=0,
        )
        return

    telemetry.send_battery(
        voltage_v=state.voltage,
        current_a=_clamp_battery_current_a(state.current),
        capacity_mah=0,
        remaining_pct=int(round(state.soc)),
    )


def _get_motor_supply_voltage(state: Optional[BatteryState]) -> float:
    if state is not None and state.voltage > 0.0:
        return state.voltage
    return config.MOTOR_LIMIT_FALLBACK_VOLTAGE


def _limit_drive_outputs(
    requested_left: float,
    requested_right: float,
    left_sample: MotorCurrentSample,
    right_sample: MotorCurrentSample,
    battery_state: Optional[BatteryState],
) -> MotorLimitResult:
    if not config.MOTOR_CURRENT_LIMITING_ENABLED:
        return MotorLimitResult(
            left_output=requested_left,
            right_output=requested_right,
            left_limited=False,
            right_limited=False,
        )

    supply_voltage_v = _get_motor_supply_voltage(battery_state)
    return apply_motor_limits(
        requested_left=requested_left,
        requested_right=requested_right,
        left_sample=left_sample,
        right_sample=right_sample,
        left_config=MotorLimitConfig(
            current_limit_a=config.LEFT_MOTOR_MAX_CURRENT_A,
            power_limit_w=config.LEFT_MOTOR_MAX_POWER_W,
            supply_voltage_v=supply_voltage_v,
        ),
        right_config=MotorLimitConfig(
            current_limit_a=config.RIGHT_MOTOR_MAX_CURRENT_A,
            power_limit_w=config.RIGHT_MOTOR_MAX_POWER_W,
            supply_voltage_v=supply_voltage_v,
        ),
    )


def _telemetry_motor_current_a(sample: MotorCurrentSample) -> float:
    if not sample.valid or sample.current_a is None:
        return 0.0
    return max(0.0, sample.current_a)


def _create_motor_current_reader():
    if not config.MOTOR_CURRENT_SENSE_ENABLED:
        return NullMotorCurrentReader()

    sample_rate_sps = int(round(config.MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ))
    try:
        return open_ads1115_current_reader(
            address=config.MOTOR_CURRENT_SENSE_I2C_ADDRESS,
            left_channel=config.MOTOR_CURRENT_SENSE_LEFT_CHANNEL,
            right_channel=config.MOTOR_CURRENT_SENSE_RIGHT_CHANNEL,
            gain=config.MOTOR_CURRENT_SENSE_GAIN,
            sample_rate_sps=sample_rate_sps,
            left_calibration=MotorCurrentCalibration(
                zero_offset_v=config.LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V,
                amps_per_volt=config.LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT,
            ),
            right_calibration=MotorCurrentCalibration(
                zero_offset_v=config.RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V,
                amps_per_volt=config.RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT,
            ),
        )
    except Exception as exc:
        LOGGER.warning("Motor current sensing disabled: failed to initialize ADS1115 reader: %s", exc)
        return NullMotorCurrentReader()


def main() -> int:
    """Run the BiBa control loop until a shutdown signal is received."""
    _setup_logging()

    if config.VOICE_AUDITION_ENABLED:
        LOGGER.info("BiBa controller started in voice audition mode")
        return _run_voice_audition_mode()

    receiver = CRSFReceiver(config.CRSF_PORT, config.CRSF_BAUD, config.SERIAL_TIMEOUT_S)
    telemetry = CRSFTelemetry(None)
    bms = _create_bms()
    bms_poller: Optional[BMSPoller] = None
    current_reader = _create_motor_current_reader()
    stats = SystemStats()
    pi = _connect_pigpio()
    if pi.connected:
        left_motor, right_motor = _create_motor_pair(pi)
        drive = DifferentialDrive(left_motor, right_motor)
        buzzer = _create_buzzer(pi)
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
        if config.BMS_TRANSPORT == "BLE":
            LOGGER.warning("Daly BMS unavailable via BLE %s: %s", config.BMS_BLE_ADDRESS or "<unset>", exc)
        else:
            LOGGER.warning("Daly BMS unavailable on %s: %s", config.BMS_PORT, exc)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    armed = False
    had_connection = False
    low_voltage_active = False
    melody_zone = -1
    left_current_sample = MotorCurrentSample(current_a=None, valid=False)
    right_current_sample = MotorCurrentSample(current_a=None, valid=False)
    last_frame_time = time.monotonic()
    last_drive_update_at: float | None = None
    last_telemetry_send = 0.0
    last_battery_telemetry_log = 0.0
    battery_telemetry_cleared = False
    _last_debug_log = 0.0
    loop_period = 1.0 / max(config.MAIN_LOOP_HZ, 1)
    throttle_filter = _create_throttle_filter()
    voice_selector = VoiceSelector(config.VOICE_SELECTION_MODE)

    LOGGER.info("BiBa controller started")
    if config.STARTUP_VOICE_ENABLED and _play_grouped_voice(
        voice_selector,
        "startup",
        config.STARTUP_VOICES,
        buzzer,
    ):
        pass
    elif config.STARTUP_MELODY:
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
                    if not _play_grouped_voice(
                        voice_selector,
                        "connected",
                        config.CONNECTED_VOICES,
                        buzzer,
                    ):
                        buzzer.connected_tone()
                beacon.on_connected()

                requested_armed = _is_armed(channels)
                if requested_armed != armed:
                    arm_state_changed = True
                    armed = requested_armed
                    if armed:
                        LOGGER.info("Platform armed")
                        if config.ARM_VOICE_ENABLED and _play_grouped_voice(
                            voice_selector,
                            "arm",
                            config.ARM_VOICES,
                            buzzer,
                        ):
                            pass
                        else:
                            buzzer.arm_tone()
                    else:
                        LOGGER.info("Platform disarmed")
                        if not _play_grouped_voice(
                            voice_selector,
                            "disarm",
                            config.DISARM_VOICES,
                            buzzer,
                        ):
                            buzzer.disarm_tone()

                raw_throttle = _get_channel(channels, config.CH_THROTTLE)

                throttle = raw_throttle
                if throttle_filter is not None:
                    throttle = throttle_filter.update(raw_throttle)
                steering = _get_channel(channels, config.CH_STEERING)
                arm_ch = _get_channel(channels, config.CH_ARM)
                control_active = armed and (
                    abs(raw_throttle) > config.MOTOR_DEADBAND or abs(steering) > config.MOTOR_DEADBAND
                )
                buzzer.set_control_active(control_active)
                control_dt = loop_period if last_drive_update_at is None else max(0.0, loop_started_at - last_drive_update_at)
                battery_state = bms_poller.latest_state if bms_poller else None
                if armed:
                    if hasattr(drive, "mix_and_ramp") and hasattr(drive, "apply_output"):
                        requested_left, requested_right = drive.mix_and_ramp(throttle, steering, control_dt)
                        left_sample, right_sample = current_reader.read_currents()
                        left_current_sample = left_sample
                        right_current_sample = right_sample
                        limited = _limit_drive_outputs(
                            requested_left=requested_left,
                            requested_right=requested_right,
                            left_sample=left_sample,
                            right_sample=right_sample,
                            battery_state=battery_state,
                        )
                        left_duty, right_duty = drive.apply_output(
                            limited.left_output,
                            limited.right_output,
                            throttle=throttle,
                            steering=steering,
                            dt=control_dt,
                        )
                    else:
                        left_duty, right_duty = drive.drive(throttle, steering, control_dt)
                else:
                    if throttle_filter is not None:
                        throttle_filter.reset()
                    if hasattr(drive, "mix_and_ramp") and hasattr(drive, "apply_output"):
                        requested_left, requested_right = drive.mix_and_ramp(0.0, 0.0, control_dt)
                        left_current_sample = MotorCurrentSample(current_a=0.0)
                        right_current_sample = MotorCurrentSample(current_a=0.0)
                        left_duty, right_duty = drive.apply_output(
                            requested_left,
                            requested_right,
                            throttle=0.0,
                            steering=0.0,
                            dt=control_dt,
                        )
                    else:
                        left_duty, right_duty = drive.drive(0.0, 0.0, control_dt)
                last_drive_update_at = loop_started_at
                if loop_started_at - _last_debug_log >= 1.0:
                    _last_debug_log = loop_started_at
                    ch_vals = [f"{v:+.2f}" for v in channels[:6]]
                    LOGGER.info(
                        "CH[%s] raw_thr=%.2f thr=%.2f str=%.2f lm=%.3f rm=%.3f arm_ch=%.2f armed=%s",
                        ",".join(ch_vals), raw_throttle, throttle, steering,
                        left_duty, right_duty, arm_ch, armed,
                    )

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
                    if not _play_grouped_voice(
                        voice_selector,
                        "failsafe",
                        config.FAILSAFE_VOICES,
                        buzzer,
                    ):
                        buzzer.failsafe_tone()
                if throttle_filter is not None:
                    throttle_filter.reset()
                control_dt = loop_period if last_drive_update_at is None else max(0.0, loop_started_at - last_drive_update_at)
                drive.drive(0.0, 0.0, control_dt)
                last_drive_update_at = loop_started_at
                if had_connection:
                    had_connection = False
                    if not _play_grouped_voice(
                        voice_selector,
                        "disconnected",
                        config.DISCONNECTED_VOICES,
                        buzzer,
                    ):
                        buzzer.disconnected_tone()
                armed = False
                beacon.on_failsafe(loop_started_at)

            if beacon.should_sos(loop_started_at):
                buzzer.sos_beacon()

            if loop_started_at - last_telemetry_send >= config.BMS_POLL_INTERVAL_S:
                last_telemetry_send = loop_started_at
                battery_state = bms_poller.latest_state if bms_poller else None

                try:
                    if battery_state is None:
                        if not battery_telemetry_cleared:
                            _send_battery_telemetry(telemetry, battery_state)
                            battery_telemetry_cleared = True
                    else:
                        _send_battery_telemetry(telemetry, battery_state)
                        battery_telemetry_cleared = False
                        last_battery_telemetry_log = _log_battery_telemetry(
                            battery_state,
                            now=loop_started_at,
                            last_log_at=last_battery_telemetry_log,
                        )
                except Exception as exc:
                    LOGGER.warning("Failed to send CRSF battery telemetry: %s", exc)

                try:
                    _send_system_telemetry(
                        telemetry,
                        stats,
                        left_current_a=_telemetry_motor_current_a(left_current_sample),
                        right_current_a=_telemetry_motor_current_a(right_current_sample),
                    )
                except Exception as exc:
                    LOGGER.warning("Failed to send CRSF system telemetry: %s", exc)

                if battery_state is not None:
                    is_low_voltage = _battery_is_low(battery_state)
                    if is_low_voltage and not low_voltage_active:
                        low_voltage_active = True
                        LOGGER.warning("Low battery warning: %.2fV", battery_state.voltage)
                        if not _play_grouped_voice(
                            voice_selector,
                            "low_voltage",
                            config.LOW_VOLTAGE_VOICES,
                            buzzer,
                        ):
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
        current_reader.close()
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