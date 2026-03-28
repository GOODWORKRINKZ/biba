"""Runtime configuration for the BiBa controller."""

from __future__ import annotations

import os


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_env_choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().upper()
    if normalized in choices:
        return normalized
    return default


def _get_env_list(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(";") if item.strip()]


MOTOR_DRIVER_TYPE = _get_env_choice("MOTOR_DRIVER_TYPE", "BTS7960", {"PWM_DIR", "BTS7960"})
BTS7960_PWM_MODE = _get_env_choice("BTS7960_PWM_MODE", "HARDWARE", {"HARDWARE", "SOFTWARE"})
MOTOR1_PWM = _get_env_int("MOTOR1_PWM", 18)
MOTOR1_DIR = _get_env_int("MOTOR1_DIR", 23)
MOTOR2_PWM = _get_env_int("MOTOR2_PWM", 13)
MOTOR2_DIR = _get_env_int("MOTOR2_DIR", 24)
LEFT_MOTOR_RPWM = _get_env_int("LEFT_MOTOR_RPWM", 18)
LEFT_MOTOR_LPWM = _get_env_int("LEFT_MOTOR_LPWM", 13)
LEFT_MOTOR_REN = _get_env_int("LEFT_MOTOR_REN", 23)
LEFT_MOTOR_LEN = _get_env_int("LEFT_MOTOR_LEN", 24)
LEFT_MOTOR_ENABLED = bool(_get_env_int("LEFT_MOTOR_ENABLED", 1))
RIGHT_MOTOR_RPWM = _get_env_int("RIGHT_MOTOR_RPWM", 12)
RIGHT_MOTOR_LPWM = _get_env_int("RIGHT_MOTOR_LPWM", 19)
RIGHT_MOTOR_REN = _get_env_int("RIGHT_MOTOR_REN", 20)
RIGHT_MOTOR_LEN = _get_env_int("RIGHT_MOTOR_LEN", 21)
RIGHT_MOTOR_ENABLED = bool(_get_env_int("RIGHT_MOTOR_ENABLED", 1))
MOTOR1_INVERTED = _get_env_int("MOTOR1_INVERTED", 0)
MOTOR2_INVERTED = _get_env_int("MOTOR2_INVERTED", 0)
BUZZER_PIN = _get_env_int("BUZZER_PIN", 17)
MOTOR_CURRENT_LIMITING_ENABLED = bool(_get_env_int("MOTOR_CURRENT_LIMITING_ENABLED", 0))
MOTOR_CURRENT_SENSE_ENABLED = bool(_get_env_int("MOTOR_CURRENT_SENSE_ENABLED", 0))
MOTOR_CURRENT_SENSE_I2C_ADDRESS = _get_env_int("MOTOR_CURRENT_SENSE_I2C_ADDRESS", 0x48)
MOTOR_CURRENT_SENSE_LEFT_CHANNEL = _get_env_int("MOTOR_CURRENT_SENSE_LEFT_CHANNEL", 0)
MOTOR_CURRENT_SENSE_RIGHT_CHANNEL = _get_env_int("MOTOR_CURRENT_SENSE_RIGHT_CHANNEL", 1)
MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ = _get_env_float("MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ", 25.0)
MOTOR_CURRENT_SENSE_GAIN = os.getenv("MOTOR_CURRENT_SENSE_GAIN", "1")
LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V = _get_env_float("LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V", 0.0)
RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V = _get_env_float("RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V", 0.0)
LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT = _get_env_float("LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT", 1.0)
RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT = _get_env_float("RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT", 1.0)
LEFT_MOTOR_MAX_CURRENT_A = _get_env_float("LEFT_MOTOR_MAX_CURRENT_A", 18.0)
RIGHT_MOTOR_MAX_CURRENT_A = _get_env_float("RIGHT_MOTOR_MAX_CURRENT_A", 18.0)
LEFT_MOTOR_MAX_POWER_W = _get_env_float("LEFT_MOTOR_MAX_POWER_W", 180.0)
RIGHT_MOTOR_MAX_POWER_W = _get_env_float("RIGHT_MOTOR_MAX_POWER_W", 180.0)
MOTOR_LIMIT_FALLBACK_VOLTAGE = _get_env_float("MOTOR_LIMIT_FALLBACK_VOLTAGE", 24.0)

CRSF_PORT = os.getenv("CRSF_PORT", "/dev/ttyS0")
CRSF_BAUD = _get_env_int("CRSF_BAUD", 420000)
BMS_TRANSPORT = _get_env_choice("BMS_TRANSPORT", "BLE", {"UART", "BLE"})
BMS_PORT = os.getenv("BMS_PORT", "/dev/ttyUSB0")
BMS_BAUD = _get_env_int("BMS_BAUD", 9600)
BMS_BLE_ADDRESS = os.getenv("BMS_BLE_ADDRESS", "")
BMS_BLE_SERVICE_UUID = os.getenv("BMS_BLE_SERVICE_UUID", "0000fff0-0000-1000-8000-00805f9b34fb")
BMS_BLE_WRITE_UUID = os.getenv("BMS_BLE_WRITE_UUID", "0000fff2-0000-1000-8000-00805f9b34fb")
BMS_BLE_NOTIFY_UUID = os.getenv("BMS_BLE_NOTIFY_UUID", "0000fff1-0000-1000-8000-00805f9b34fb")
BMS_BLE_TIMEOUT_S = _get_env_float("BMS_BLE_TIMEOUT_S", 1.5)

FAILSAFE_TIMEOUT_S = _get_env_float("FAILSAFE_TIMEOUT_S", 0.5)
MAIN_LOOP_HZ = _get_env_int("MAIN_LOOP_HZ", 50)
BMS_POLL_INTERVAL_S = _get_env_float("BMS_POLL_INTERVAL_S", 1.0)
TEST_BATTERY_VOLTAGE = _get_env_float("TEST_BATTERY_VOLTAGE", 25.0)
TEST_BATTERY_CURRENT = _get_env_float("TEST_BATTERY_CURRENT", 1.2)
TEST_BATTERY_CAPACITY_MAH = _get_env_int("TEST_BATTERY_CAPACITY_MAH", 0)
TEST_BATTERY_REMAINING_PCT = _get_env_int("TEST_BATTERY_REMAINING_PCT", 55)

CH_STEERING = _get_env_int("CH_STEERING", 3)
CH_THROTTLE = _get_env_int("CH_THROTTLE", 1)
CH_ARM = _get_env_int("CH_ARM", 4)
ARM_THRESHOLD = _get_env_float("ARM_THRESHOLD", 0.3)
THROTTLE_FILTER_MODE = _get_env_choice("THROTTLE_FILTER_MODE", "NONE", {"NONE", "KALMAN"})
THROTTLE_KALMAN_PROCESS_NOISE = _get_env_float("THROTTLE_KALMAN_PROCESS_NOISE", 0.02)
THROTTLE_KALMAN_MEASUREMENT_NOISE = _get_env_float("THROTTLE_KALMAN_MEASUREMENT_NOISE", 0.5)

LOW_CELL_VOLTAGE = _get_env_float("LOW_CELL_VOLTAGE", 3.5)
LOW_PACK_VOLTAGE = _get_env_float("LOW_PACK_VOLTAGE", 21.0)
PWM_FREQUENCY_HZ = _get_env_int("PWM_FREQUENCY_HZ", 20000)
SERIAL_TIMEOUT_S = _get_env_float("SERIAL_TIMEOUT_S", 0.02)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Motor ramping / slew rate
RAMP_ACCEL_RATE = _get_env_float("RAMP_ACCEL_RATE", 2.0)
RAMP_DECEL_RATE = _get_env_float("RAMP_DECEL_RATE", 0.5)
RAMP_REVERSE_DECEL_RATE = _get_env_float("RAMP_REVERSE_DECEL_RATE", 0.5)
RAMP_ZERO_HOLD_S = _get_env_float("RAMP_ZERO_HOLD_S", 0.15)
MOTOR_DEADBAND = _get_env_float("MOTOR_DEADBAND", 0.05)

# Beacon / SOS
BEACON_ENABLED = bool(_get_env_int("BEACON_ENABLED", 1))
BEACON_DELAY_S = _get_env_float("BEACON_DELAY_S", 300.0)
CH_BEACON = _get_env_int("CH_BEACON", 7)

# Melody selection
ENABLE_RC_MELODIES = bool(_get_env_int("ENABLE_RC_MELODIES", 0))
CH_MELODY = _get_env_int("CH_MELODY", 8)
STARTUP_MELODY = os.getenv("STARTUP_MELODY", "biba_signature")

# Voice (WAV playback through motor coils)
VOICE_SELECTION_MODE = _get_env_choice("VOICE_SELECTION_MODE", "ROUND_ROBIN", {"ROUND_ROBIN", "RANDOM"})
VOICE_AUDITION_ENABLED = bool(_get_env_int("VOICE_AUDITION_ENABLED", 0))
VOICE_AUDITION_MANIFEST = os.getenv("VOICE_AUDITION_MANIFEST", "")
STARTUP_VOICES = _get_env_list(
    "STARTUP_VOICES",
    "/app/voice/startup_returned.wav",
)
STARTUP_VOICE_ENABLED = bool(_get_env_int("STARTUP_VOICE_ENABLED", 1))
STARTUP_VOICE = STARTUP_VOICES[0] if STARTUP_VOICES else ""
ARM_VOICES = _get_env_list(
    "ARM_VOICES",
    "/app/voice/arm_begin.wav",
)
ARM_VOICE_ENABLED = bool(_get_env_int("ARM_VOICE_ENABLED", 1))
ARM_VOICE = ARM_VOICES[0] if ARM_VOICES else ""
DISARM_VOICES = _get_env_list(
    "DISARM_VOICES",
    "/app/voice/disarm_waiting.wav",
)
CONNECTED_VOICES = _get_env_list(
    "CONNECTED_VOICES",
    "/app/voice/connected_online.wav",
)
DISCONNECTED_VOICES = _get_env_list(
    "DISCONNECTED_VOICES",
    "/app/voice/disconnected_protocol.wav",
)
FAILSAFE_VOICES = _get_env_list(
    "FAILSAFE_VOICES",
    "/app/voice/failsafe_intruder.wav",
)
LOW_VOLTAGE_VOICES = _get_env_list(
    "LOW_VOLTAGE_VOICES",
    "/app/voice/low_voltage_retribution.wav",
)
SOS_VOICES = _get_env_list(
    "SOS_VOICES",
    "/app/voice/sos_comply.wav",
)
