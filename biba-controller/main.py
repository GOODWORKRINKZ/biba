"""Main runtime loop for the BiBa wheeled platform controller."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone
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
from crsf.telemetry import CRSFTelemetry, build_biba_system_metrics
from motors.current_control import MotorCurrentSample, MotorLimitConfig, MotorLimitResult, apply_motor_limits
from motors.current_sense import MotorCurrentCalibration, NullMotorCurrentReader, open_ads1115_current_reader
from motors.driver import BTS7960MotorDriver, DifferentialDrive, MotorDriver
from motors.ramping import ScalarKalmanFilter
from system_stats import SystemStats

LOGGER = logging.getLogger("biba-controller")
RUNNING = True
_BATTERY_TELEMETRY_LOG_INTERVAL_S = 5.0
_BATTERY_DIRECTION_MASK = 0b00011
_BATTERY_STATUS_ARMED = 0b00100
_BATTERY_STATUS_MUTED = 0b01000
_BATTERY_STATUS_BEACON = 0b10000
_BATTERY_STATUS_TRIM_MODE = 0b100000
_TRIM_GESTURE_CHANNEL_COUNT = 4
_TRIM_GESTURE_HIGH_THRESHOLD = 0.9


def _clamp_motor_trim(trim: float) -> float:
    return max(-config.MOTOR_TRIM_MAX_EFFECT, min(config.MOTOR_TRIM_MAX_EFFECT, trim))


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

    def play_wav_async(self, path: str) -> None:
        del path

    def play_spectral_async(self, path: str) -> None:
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


def _play_grouped_voice_async(
    selector: VoiceSelector,
    event: str,
    voices: list[str],
    buzzer,
) -> bool:
    path = selector.choose(event, voices)
    if path is None:
        return False

    player = getattr(buzzer, "play_spectral_async", None)
    if player is None:
        player = getattr(buzzer, "play_wav_async", None)
    if player is not None:
        player(path)
        return True

    player = getattr(buzzer, "play_spectral", None)
    if player is None:
        player = buzzer.play_wav
    threading.Thread(target=player, args=(path,), daemon=True).start()
    return True


def _play_grouped_voice_if_allowed(
    selector: VoiceSelector,
    event: str,
    voices: list[str],
    buzzer,
    *,
    mute_active: bool,
    allow_when_muted: bool = False,
) -> bool:
    if mute_active and not allow_when_muted:
        return False
    return _play_grouped_voice(selector, event, voices, buzzer)


def _play_grouped_voice_async_if_allowed(
    selector: VoiceSelector,
    event: str,
    voices: list[str],
    buzzer,
    *,
    mute_active: bool,
    allow_when_muted: bool = False,
) -> bool:
    if mute_active and not allow_when_muted:
        return False
    return _play_grouped_voice_async(selector, event, voices, buzzer)


def _play_buzzer_method_async(buzzer, method_name: str) -> None:
    player = getattr(buzzer, f"{method_name}_async", None)
    if player is not None:
        player()
        return

    player = getattr(buzzer, method_name)
    threading.Thread(target=player, daemon=True).start()


def _play_buzzer_method_async_if_allowed(
    buzzer,
    method_name: str,
    *,
    mute_active: bool,
    allow_when_muted: bool = False,
) -> bool:
    if mute_active and not allow_when_muted:
        return False
    _play_buzzer_method_async(buzzer, method_name)
    return True


def _play_named_async_if_allowed(
    buzzer,
    name: str,
    *,
    mute_active: bool,
    allow_when_muted: bool = False,
) -> bool:
    if mute_active and not allow_when_muted:
        return False
    buzzer.play_named_async(name)
    return True


def _replay_current_audio_state_after_unmute(
    voice_selector: VoiceSelector,
    buzzer,
    *,
    connected: bool,
    armed: bool,
) -> bool:
    if armed:
        if config.ARM_VOICE_ENABLED and _play_grouped_voice_async_if_allowed(
            voice_selector,
            "arm",
            config.ARM_VOICES,
            buzzer,
            mute_active=False,
        ):
            return True
        return _play_buzzer_method_async_if_allowed(
            buzzer,
            "arm_tone",
            mute_active=False,
        )

    if connected:
        if _play_grouped_voice_async_if_allowed(
            voice_selector,
            "connected",
            config.CONNECTED_VOICES,
            buzzer,
            mute_active=False,
        ):
            return True
        return _play_buzzer_method_async_if_allowed(
            buzzer,
            "connected_tone",
            mute_active=False,
        )

    return False


def _create_synth_pins() -> tuple[list[int], list[int]]:
    left_pwm_pins, left_comp_pins, right_pwm_pins, right_comp_pins = _create_synth_motor_groups()
    return left_pwm_pins + right_pwm_pins, left_comp_pins + right_comp_pins


def _create_synth_motor_groups() -> tuple[list[int], list[int], list[int], list[int]]:
    left_pwm_pins: list[int] = []
    left_comp_pins: list[int] = []
    right_pwm_pins: list[int] = []
    right_comp_pins: list[int] = []
    if config.LEFT_MOTOR_ENABLED:
        left_pwm_pins.append(config.LEFT_MOTOR_RPWM)
        left_comp_pins.append(config.LEFT_MOTOR_LPWM)
    if config.RIGHT_MOTOR_ENABLED:
        right_pwm_pins.append(config.RIGHT_MOTOR_RPWM)
        right_comp_pins.append(config.RIGHT_MOTOR_LPWM)
    return left_pwm_pins, left_comp_pins, right_pwm_pins, right_comp_pins


def _create_buzzer(pi: pigpio.pi):
    synth_pwm_pins, synth_comp_pins = _create_synth_pins()
    left_pwm_pins, left_comp_pins, right_pwm_pins, right_comp_pins = _create_synth_motor_groups()
    return MotorSynth(
        pi,
        synth_pwm_pins,
        comp_pins=synth_comp_pins,
        left_pwm_pins=left_pwm_pins,
        left_comp_pins=left_comp_pins,
        right_pwm_pins=right_pwm_pins,
        right_comp_pins=right_comp_pins,
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


def _is_muted(channels: list[float]) -> bool:
    return _get_channel(channels, config.CH_MUTE) > config.ARM_THRESHOLD


def _get_channel(channels: list[float], index: int) -> float:
    if index >= len(channels):
        return 0.0
    return channels[index]


def _trim_gesture_active(channels: list[float]) -> bool:
    for index in range(_TRIM_GESTURE_CHANNEL_COUNT):
        if _get_channel(channels, index) < _TRIM_GESTURE_HIGH_THRESHOLD:
            return False
    return True


def _live_motor_trim_from_channels(channels: list[float]) -> float:
    return _clamp_motor_trim(_get_channel(channels, config.CH_TRIM) * config.MOTOR_TRIM_MAX_EFFECT)


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
    metrics = build_biba_system_metrics(
        cpu_pct=stats.cpu_percent(),
        mem_pct=stats.memory_percent(),
        left_motor_current_a=max(0.0, left_current_a),
        right_motor_current_a=max(0.0, right_current_a),
    )
    telemetry.send_system_stats(metrics=metrics)


def _battery_telemetry_current_a(current_a: float) -> float:
    return abs(current_a)


def _battery_telemetry_direction_code(current_a: float) -> int:
    if current_a > 0.0:
        return 1
    if current_a < 0.0:
        return 2
    return 0


def _battery_telemetry_direction_label(current_a: float) -> str:
    direction_code = _battery_telemetry_direction_code(current_a)
    if direction_code == 1:
        return "CHG"
    if direction_code == 2:
        return "DIS"
    return "IDLE"


def _apply_motor_trim(left_duty: float, right_duty: float, trim: float) -> tuple[float, float]:
    clamped_trim = _clamp_motor_trim(trim)
    if clamped_trim > 0.0:
        return left_duty, right_duty * (1.0 - clamped_trim)
    if clamped_trim < 0.0:
        return left_duty * (1.0 - abs(clamped_trim)), right_duty
    return left_duty, right_duty


def _load_saved_motor_trim() -> float:
    settings_path = Path(config.MOTOR_TRIM_SETTINGS_PATH)
    if not settings_path.exists():
        return 0.0

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        trim = float(payload.get("trim", 0.0))
    except Exception as exc:
        LOGGER.warning("Failed to load motor trim settings from %s: %s", settings_path, exc)
        return 0.0

    return _clamp_motor_trim(trim)


def _save_motor_trim(trim: float) -> None:
    settings_path = Path(config.MOTOR_TRIM_SETTINGS_PATH)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = settings_path.with_name(f"{settings_path.name}.tmp")
    payload = {
        "trim": _clamp_motor_trim(trim),
        "updated_at": time.time(),
    }
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, settings_path)


def _encode_battery_status_bits(
    current_a: float,
    *,
    armed: bool,
    mute_active: bool,
    beacon_active: bool,
    trim_mode_active: bool = False,
) -> int:
    status_bits = _battery_telemetry_direction_code(current_a) & _BATTERY_DIRECTION_MASK
    if armed:
        status_bits |= _BATTERY_STATUS_ARMED
    if mute_active:
        status_bits |= _BATTERY_STATUS_MUTED
    if beacon_active:
        status_bits |= _BATTERY_STATUS_BEACON
    if trim_mode_active:
        status_bits |= _BATTERY_STATUS_TRIM_MODE
    return status_bits


def _encode_crsf_current_da(current_a: float) -> int:
    return max(0, int(round(current_a * 10)))


def _log_battery_telemetry(state: BatteryState, now: float, last_log_at: float) -> float:
    if now - last_log_at < _BATTERY_TELEMETRY_LOG_INTERVAL_S:
        return last_log_at

    telemetry_current_a = _battery_telemetry_current_a(state.current)
    telemetry_direction = _battery_telemetry_direction_label(state.current)
    LOGGER.info(
        (
            "Battery telemetry raw_current_a=%.2f telemetry_current_a=%.2f "
            "crsf_current_da=%d telemetry_direction=%s voltage_v=%.2f soc_pct=%d"
        ),
        state.current,
        telemetry_current_a,
        _encode_crsf_current_da(telemetry_current_a),
        telemetry_direction,
        state.voltage,
        int(round(state.soc)),
    )
    return now


def _trace_battery_telemetry(stage: str, state: Optional[BatteryState], timestamp_s: float) -> None:
    if not config.BMS_TELEMETRY_TRACE_ENABLED:
        return

    if state is None:
        LOGGER.info("Battery telemetry trace stage=%s t=%.6f state=none", stage, timestamp_s)
        return

    LOGGER.info(
        (
            "Battery telemetry trace stage=%s t=%.6f raw_current_a=%.2f "
            "telemetry_current_a=%.2f voltage_v=%.2f soc_pct=%d"
        ),
        stage,
        timestamp_s,
        state.current,
        _battery_telemetry_current_a(state.current),
        state.voltage,
        int(round(state.soc)),
    )


def _send_battery_telemetry(
    telemetry: CRSFTelemetry,
    state: Optional[BatteryState],
    *,
    consumed_at_s: float | None = None,
    armed: bool = False,
    mute_active: bool = False,
    beacon_active: bool = False,
    trim_mode_active: bool = False,
) -> None:
    if consumed_at_s is not None:
        _trace_battery_telemetry("consume", state, consumed_at_s)

    status_bits = _encode_battery_status_bits(
        0.0 if state is None else state.current,
        armed=armed,
        mute_active=mute_active,
        beacon_active=beacon_active,
        trim_mode_active=trim_mode_active,
    )

    if state is None:
        telemetry.send_battery(
            voltage_v=0.0,
            current_a=0.0,
            capacity_mah=status_bits,
            remaining_pct=0,
        )
        _trace_battery_telemetry("send", state, time.monotonic())
        return

    telemetry.send_battery(
        voltage_v=state.voltage,
        current_a=_battery_telemetry_current_a(state.current),
        capacity_mah=status_bits,
        remaining_pct=int(round(state.soc)),
    )
    _trace_battery_telemetry("send", state, time.monotonic())


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


def _motor_current_trace_has_activity(
    *,
    raw_throttle: float,
    steering: float,
    left_duty: float,
    right_duty: float,
    left_sample: MotorCurrentSample,
    right_sample: MotorCurrentSample,
) -> bool:
    if abs(raw_throttle) > config.MOTOR_DEADBAND or abs(steering) > config.MOTOR_DEADBAND:
        return True
    if abs(left_duty) > 1e-6 or abs(right_duty) > 1e-6:
        return True
    if _telemetry_motor_current_a(left_sample) > 0.0 or _telemetry_motor_current_a(right_sample) > 0.0:
        return True
    return False


def _update_motor_current_trace_window(
    *,
    armed: bool,
    raw_throttle: float,
    steering: float,
    left_duty: float,
    right_duty: float,
    left_sample: MotorCurrentSample,
    right_sample: MotorCurrentSample,
    now_s: float,
    last_activity_at_s: float | None,
) -> tuple[bool, float | None]:
    if not armed:
        return False, None

    activity_now = _motor_current_trace_has_activity(
        raw_throttle=raw_throttle,
        steering=steering,
        left_duty=left_duty,
        right_duty=right_duty,
        left_sample=left_sample,
        right_sample=right_sample,
    )
    if activity_now:
        return True, now_s

    if last_activity_at_s is None:
        return False, None

    if now_s - last_activity_at_s <= config.MOTOR_CURRENT_TRACE_POST_ROLL_S:
        return True, last_activity_at_s

    return False, None


def _build_motor_current_trace_record(
    *,
    session_id: str,
    sample_index: int,
    now_s: float,
    wall_time_iso: str,
    armed: bool,
    raw_throttle: float,
    filtered_throttle: float,
    steering: float,
    control_active: bool,
    requested_left: float,
    requested_right: float,
    limited_left: float,
    limited_right: float,
    trimmed_left: float,
    trimmed_right: float,
    left_duty: float,
    right_duty: float,
    left_sample: MotorCurrentSample,
    right_sample: MotorCurrentSample,
    battery_state: Optional[BatteryState],
    bms_sample_monotonic_s: float | None,
    mute_active: bool,
    beacon_active: bool,
    trim_mode_active: bool,
    trace_reason: str,
) -> dict[str, object]:
    bms_age_s = None if bms_sample_monotonic_s is None else max(0.0, now_s - bms_sample_monotonic_s)

    return {
        "session_id": session_id,
        "sample_index": sample_index,
        "monotonic_s": now_s,
        "wall_time_iso": wall_time_iso,
        "armed": armed,
        "raw_throttle": raw_throttle,
        "filtered_throttle": filtered_throttle,
        "steering": steering,
        "control_active": control_active,
        "requested_left": requested_left,
        "requested_right": requested_right,
        "limited_left": limited_left,
        "limited_right": limited_right,
        "trimmed_left": trimmed_left,
        "trimmed_right": trimmed_right,
        "left_duty": left_duty,
        "right_duty": right_duty,
        "left_current_valid": left_sample.valid,
        "right_current_valid": right_sample.valid,
        "left_current_a": left_sample.current_a,
        "right_current_a": right_sample.current_a,
        "left_voltage_v": left_sample.voltage_v,
        "right_voltage_v": right_sample.voltage_v,
        "left_raw_adc": left_sample.raw_adc,
        "right_raw_adc": right_sample.raw_adc,
        "left_active_channel": left_sample.channel,
        "right_active_channel": right_sample.channel,
        "left_channel": left_sample.channel,
        "right_channel": right_sample.channel,
        "bms_present": battery_state is not None,
        "bms_current_a": None if battery_state is None else battery_state.current,
        "bms_voltage_v": None if battery_state is None else battery_state.voltage,
        "bms_soc_pct": None if battery_state is None else battery_state.soc,
        "bms_sample_monotonic_s": bms_sample_monotonic_s,
        "bms_age_s": bms_age_s,
        "mute_active": mute_active,
        "beacon_active": beacon_active,
        "trim_mode_active": trim_mode_active,
        "trace_reason": trace_reason,
    }


def _append_jsonl_record(path: str, record: dict[str, object]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as output_file:
        output_file.write(json.dumps(record, sort_keys=True) + "\n")


def _current_trace_wall_time_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _create_motor_current_reader():
    if not config.MOTOR_CURRENT_SENSE_ENABLED:
        return NullMotorCurrentReader()

    sample_rate_sps = int(round(config.MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ))
    try:
        return open_ads1115_current_reader(
            address=config.MOTOR_CURRENT_SENSE_I2C_ADDRESS,
            left_forward_channel=config.LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL,
            left_reverse_channel=config.LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL,
            right_forward_channel=config.RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL,
            right_reverse_channel=config.RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL,
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
    mute_active = False
    beacon_active = False
    trim_mode_active = False
    had_connection = False
    low_voltage_active = False
    melody_zone = -1
    saved_motor_trim = _load_saved_motor_trim()
    trim_gesture_started_at: float | None = None
    trim_gesture_consumed = False
    left_current_sample = MotorCurrentSample(current_a=None, valid=False)
    right_current_sample = MotorCurrentSample(current_a=None, valid=False)
    last_frame_time = time.monotonic()
    last_drive_update_at: float | None = None
    last_telemetry_send = 0.0
    last_battery_telemetry_log = 0.0
    battery_telemetry_cleared = False
    trace_session_id = f"{int(time.time() * 1000)}-{os.getpid()}"
    trace_sample_index = 0
    trace_last_activity_at_s: float | None = None
    trace_last_log_at_s: float | None = None
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
                connection_state_changed = False
                was_muted = mute_active
                mute_active = _is_muted(channels)

                if not had_connection:
                    connection_state_changed = True
                    had_connection = True
                    if not _play_grouped_voice_async_if_allowed(
                        voice_selector,
                        "connected",
                        config.CONNECTED_VOICES,
                        buzzer,
                        mute_active=mute_active,
                    ):
                        _play_buzzer_method_async_if_allowed(
                            buzzer,
                            "connected_tone",
                            mute_active=mute_active,
                        )
                beacon.on_connected()

                requested_armed = _is_armed(channels)
                if requested_armed != armed:
                    arm_state_changed = True
                    armed = requested_armed
                    if armed:
                        LOGGER.info("Platform armed")
                        if config.ARM_VOICE_ENABLED and _play_grouped_voice_async_if_allowed(
                            voice_selector,
                            "arm",
                            config.ARM_VOICES,
                            buzzer,
                            mute_active=mute_active,
                        ):
                            pass
                        else:
                            _play_buzzer_method_async_if_allowed(
                                buzzer,
                                "arm_tone",
                                mute_active=mute_active,
                            )
                    else:
                        LOGGER.info("Platform disarmed")
                        if not _play_grouped_voice_async_if_allowed(
                            voice_selector,
                            "disarm",
                            config.DISARM_VOICES,
                            buzzer,
                            mute_active=mute_active,
                        ):
                            _play_buzzer_method_async_if_allowed(
                                buzzer,
                                "disarm_tone",
                                mute_active=mute_active,
                            )

                if was_muted and not mute_active and not arm_state_changed and not connection_state_changed:
                    _replay_current_audio_state_after_unmute(
                        voice_selector,
                        buzzer,
                        connected=had_connection,
                        armed=armed,
                    )

                trim_gesture_requested = (not armed) and _trim_gesture_active(channels)
                if trim_gesture_requested:
                    if trim_gesture_started_at is None:
                        trim_gesture_started_at = loop_started_at
                    elif (
                        not trim_gesture_consumed
                        and loop_started_at - trim_gesture_started_at >= config.MOTOR_TRIM_CONFIRM_HOLD_S
                    ):
                        if trim_mode_active:
                            saved_motor_trim = _live_motor_trim_from_channels(channels)
                            _save_motor_trim(saved_motor_trim)
                            trim_mode_active = False
                            _play_named_async_if_allowed(
                                buzzer,
                                "trim_exit",
                                mute_active=mute_active,
                                allow_when_muted=True,
                            )
                            LOGGER.info("Motor trim saved trim=%.3f", saved_motor_trim)
                        else:
                            trim_mode_active = True
                            _play_named_async_if_allowed(
                                buzzer,
                                "trim_enter",
                                mute_active=mute_active,
                                allow_when_muted=True,
                            )
                            LOGGER.info("Motor trim mode enabled")
                        trim_gesture_consumed = True
                else:
                    trim_gesture_started_at = None
                    trim_gesture_consumed = False

                motor_trim = _live_motor_trim_from_channels(channels) if trim_mode_active else saved_motor_trim

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
                bms_sample_monotonic_s = getattr(bms_poller, "latest_state_timestamp_s", None) if bms_poller else None
                requested_left = 0.0
                requested_right = 0.0
                limited_left = 0.0
                limited_right = 0.0
                trimmed_left = 0.0
                trimmed_right = 0.0
                if armed:
                    if hasattr(drive, "mix_and_ramp") and hasattr(drive, "apply_output"):
                        requested_left, requested_right = drive.mix_and_ramp(throttle, steering, control_dt)
                        left_sample, right_sample = current_reader.read_currents(
                            left_duty=requested_left,
                            right_duty=requested_right,
                        )
                        left_current_sample = left_sample
                        right_current_sample = right_sample
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
                        limited_left = limited.left_output
                        limited_right = limited.right_output
                        left_duty, right_duty = drive.apply_output(
                            trimmed_left,
                            trimmed_right,
                            throttle=throttle,
                            steering=steering,
                            dt=control_dt,
                        )
                    else:
                        left_duty, right_duty = drive.drive(throttle, steering, control_dt)
                        requested_left = left_duty
                        requested_right = right_duty
                        limited_left = left_duty
                        limited_right = right_duty
                        trimmed_left = left_duty
                        trimmed_right = right_duty
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
                        limited_left = requested_left
                        limited_right = requested_right
                        trimmed_left = requested_left
                        trimmed_right = requested_right
                    else:
                        left_duty, right_duty = drive.drive(0.0, 0.0, control_dt)
                        requested_left = left_duty
                        requested_right = right_duty
                        limited_left = left_duty
                        limited_right = right_duty
                        trimmed_left = left_duty
                        trimmed_right = right_duty
                last_drive_update_at = loop_started_at

                if config.MOTOR_CURRENT_TRACE_ENABLED:
                    trace_should_log, trace_last_activity_at_s = _update_motor_current_trace_window(
                        armed=armed,
                        raw_throttle=raw_throttle,
                        steering=steering,
                        left_duty=left_duty,
                        right_duty=right_duty,
                        left_sample=left_current_sample,
                        right_sample=right_current_sample,
                        now_s=loop_started_at,
                        last_activity_at_s=trace_last_activity_at_s,
                    )
                    trace_activity_now = _motor_current_trace_has_activity(
                        raw_throttle=raw_throttle,
                        steering=steering,
                        left_duty=left_duty,
                        right_duty=right_duty,
                        left_sample=left_current_sample,
                        right_sample=right_current_sample,
                    )
                    if trace_should_log:
                        if (
                            trace_last_log_at_s is None
                            or config.MOTOR_CURRENT_TRACE_MIN_INTERVAL_S <= 0.0
                            or loop_started_at - trace_last_log_at_s >= config.MOTOR_CURRENT_TRACE_MIN_INTERVAL_S
                        ):
                            trace_sample_index += 1
                            trace_record = _build_motor_current_trace_record(
                                session_id=trace_session_id,
                                sample_index=trace_sample_index,
                                now_s=loop_started_at,
                                wall_time_iso=_current_trace_wall_time_iso(),
                                armed=armed,
                                raw_throttle=raw_throttle,
                                filtered_throttle=throttle,
                                steering=steering,
                                control_active=control_active,
                                requested_left=requested_left,
                                requested_right=requested_right,
                                limited_left=limited_left,
                                limited_right=limited_right,
                                trimmed_left=trimmed_left,
                                trimmed_right=trimmed_right,
                                left_duty=left_duty,
                                right_duty=right_duty,
                                left_sample=left_current_sample,
                                right_sample=right_current_sample,
                                battery_state=battery_state,
                                bms_sample_monotonic_s=bms_sample_monotonic_s,
                                mute_active=mute_active,
                                beacon_active=beacon_active,
                                trim_mode_active=trim_mode_active,
                                trace_reason="active" if trace_activity_now else "post_roll",
                            )
                            _append_jsonl_record(config.MOTOR_CURRENT_TRACE_PATH, trace_record)
                            trace_last_log_at_s = loop_started_at

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
                beacon_active = beacon_ch > config.ARM_THRESHOLD
                beacon.set_manual(beacon_active)

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
                            _play_named_async_if_allowed(
                                buzzer,
                                FUN_PLAYLIST[melody_zone],
                                mute_active=mute_active,
                            )

            if not received_frame and drive.check_failsafe(last_frame_time):
                if armed:
                    LOGGER.warning("Failsafe triggered, disarming platform")
                    if not _play_grouped_voice_async_if_allowed(
                        voice_selector,
                        "failsafe",
                        config.FAILSAFE_VOICES,
                        buzzer,
                        mute_active=mute_active,
                    ):
                        _play_buzzer_method_async_if_allowed(
                            buzzer,
                            "failsafe_tone",
                            mute_active=mute_active,
                        )
                if throttle_filter is not None:
                    throttle_filter.reset()
                control_dt = loop_period if last_drive_update_at is None else max(0.0, loop_started_at - last_drive_update_at)
                drive.drive(0.0, 0.0, control_dt)
                last_drive_update_at = loop_started_at
                if had_connection:
                    had_connection = False
                    if not _play_grouped_voice_async_if_allowed(
                        voice_selector,
                        "disconnected",
                        config.DISCONNECTED_VOICES,
                        buzzer,
                        mute_active=mute_active,
                    ):
                        _play_buzzer_method_async_if_allowed(
                            buzzer,
                            "disconnected_tone",
                            mute_active=mute_active,
                        )
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
                            _send_battery_telemetry(
                                telemetry,
                                battery_state,
                                consumed_at_s=loop_started_at,
                                armed=armed,
                                mute_active=mute_active,
                                beacon_active=beacon_active,
                                trim_mode_active=trim_mode_active,
                            )
                            battery_telemetry_cleared = True
                    else:
                        _send_battery_telemetry(
                            telemetry,
                            battery_state,
                            consumed_at_s=loop_started_at,
                            armed=armed,
                            mute_active=mute_active,
                            beacon_active=beacon_active,
                            trim_mode_active=trim_mode_active,
                        )
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
                        if not _play_grouped_voice_async_if_allowed(
                            voice_selector,
                            "low_voltage",
                            config.LOW_VOLTAGE_VOICES,
                            buzzer,
                            mute_active=mute_active,
                        ):
                            _play_buzzer_method_async_if_allowed(
                                buzzer,
                                "low_voltage_alarm",
                                mute_active=mute_active,
                            )
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