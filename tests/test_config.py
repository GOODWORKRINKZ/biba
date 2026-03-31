from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def config_module():
    module = importlib.import_module("config")
    return module


def test_config_uses_defaults_when_environment_is_missing(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.delenv("MOTOR1_PWM", raising=False)
    monkeypatch.delenv("MOTOR_DRIVER_TYPE", raising=False)
    monkeypatch.delenv("BTS7960_PWM_MODE", raising=False)
    monkeypatch.delenv("MOTOR1_INVERTED", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("BMS_TRANSPORT", raising=False)
    monkeypatch.delenv("BMS_BLE_ADDRESS", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_LIMITING_ENABLED", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_SENSE_ENABLED", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_SENSE_I2C_ADDRESS", raising=False)
    monkeypatch.delenv("LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL", raising=False)
    monkeypatch.delenv("LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL", raising=False)
    monkeypatch.delenv("RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL", raising=False)
    monkeypatch.delenv("RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_SENSE_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("LEFT_MOTOR_MAX_CURRENT_A", raising=False)
    monkeypatch.delenv("RIGHT_MOTOR_MAX_CURRENT_A", raising=False)
    monkeypatch.delenv("LEFT_MOTOR_MAX_POWER_W", raising=False)
    monkeypatch.delenv("RIGHT_MOTOR_MAX_POWER_W", raising=False)
    monkeypatch.delenv("MOTOR_LIMIT_FALLBACK_VOLTAGE", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_TRACE_ENABLED", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_TRACE_PATH", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_TRACE_POST_ROLL_S", raising=False)
    monkeypatch.delenv("MOTOR_CURRENT_TRACE_MIN_INTERVAL_S", raising=False)

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 18
    assert module.MOTOR_DRIVER_TYPE == "BTS7960"
    assert module.BTS7960_PWM_MODE == "SOFTWARE"
    assert module.MOTOR1_INVERTED == 1
    assert module.MOTOR2_INVERTED == 0
    assert module.LEFT_MOTOR_RPWM == 12
    assert module.LEFT_MOTOR_LPWM == 18
    assert module.LEFT_MOTOR_REN == 23
    assert module.LEFT_MOTOR_LEN == 24
    assert module.LEFT_MOTOR_ENABLED is True
    assert module.RIGHT_MOTOR_RPWM == 19
    assert module.RIGHT_MOTOR_LPWM == 13
    assert module.RIGHT_MOTOR_REN == 20
    assert module.RIGHT_MOTOR_LEN == 21
    assert module.RIGHT_MOTOR_ENABLED is True
    assert module.CRSF_PORT == "/dev/ttyS0"
    assert module.BMS_TRANSPORT == "BLE"
    assert module.BMS_BLE_ADDRESS == ""
    assert module.TEST_BATTERY_VOLTAGE == pytest.approx(25.0)
    assert module.TEST_BATTERY_CURRENT == pytest.approx(1.2)
    assert module.TEST_BATTERY_CAPACITY_MAH == 0
    assert module.TEST_BATTERY_REMAINING_PCT == 55
    assert module.THROTTLE_FILTER_MODE == "NONE"
    assert module.THROTTLE_KALMAN_PROCESS_NOISE == pytest.approx(0.02)
    assert module.THROTTLE_KALMAN_MEASUREMENT_NOISE == pytest.approx(0.5)
    assert module.RAMP_ACCEL_RATE == pytest.approx(2.0)
    assert module.RAMP_DECEL_RATE == pytest.approx(0.5)
    assert module.RAMP_REVERSE_DECEL_RATE == pytest.approx(0.5)
    assert module.RAMP_ZERO_HOLD_S == pytest.approx(0.15)
    assert module.MOTOR_CURRENT_LIMITING_ENABLED is False
    assert module.MOTOR_CURRENT_SENSE_ENABLED is False
    assert module.MOTOR_CURRENT_SENSE_I2C_ADDRESS == 0x48
    assert module.LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL == 2
    assert module.LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL == 3
    assert module.RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL == 0
    assert module.RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL == 1
    assert module.MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ == 32.0
    assert module.MOTOR_CURRENT_SENSE_GAIN == "1"
    assert module.LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V == pytest.approx(0.0)
    assert module.RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V == pytest.approx(0.0)
    assert module.LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT == pytest.approx(1.0)
    assert module.RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT == pytest.approx(1.0)
    assert module.LEFT_MOTOR_MAX_CURRENT_A == pytest.approx(18.0)
    assert module.RIGHT_MOTOR_MAX_CURRENT_A == pytest.approx(18.0)
    assert module.LEFT_MOTOR_MAX_POWER_W == pytest.approx(180.0)
    assert module.RIGHT_MOTOR_MAX_POWER_W == pytest.approx(180.0)
    assert module.MOTOR_LIMIT_FALLBACK_VOLTAGE == pytest.approx(24.0)
    assert module.MOTOR_CURRENT_TRACE_ENABLED is False
    assert module.MOTOR_CURRENT_TRACE_PATH == "/data/current-trace.jsonl"
    assert module.MOTOR_CURRENT_TRACE_POST_ROLL_S == pytest.approx(2.0)
    assert module.MOTOR_CURRENT_TRACE_MIN_INTERVAL_S == pytest.approx(0.0)
    assert module.LOG_LEVEL == "INFO"


def test_config_defaults_to_single_voice_asset_per_event(
    monkeypatch: pytest.MonkeyPatch,
    config_module,
) -> None:
    for name in (
        "STARTUP_VOICES",
        "ARM_VOICES",
        "DISARM_VOICES",
        "CONNECTED_VOICES",
        "DISCONNECTED_VOICES",
        "FAILSAFE_VOICES",
        "LOW_VOLTAGE_VOICES",
        "SOS_VOICES",
    ):
        monkeypatch.delenv(name, raising=False)

    module = importlib.reload(config_module)

    assert module.STARTUP_VOICES == ["/app/voice/startup_returned.wav"]
    assert module.STARTUP_VOICE == "/app/voice/startup_returned.wav"
    assert module.ARM_VOICES == ["/app/voice/arm_begin.wav"]
    assert module.ARM_VOICE == "/app/voice/arm_begin.wav"
    assert module.DISARM_VOICES == ["/app/voice/disarm_waiting.wav"]
    assert module.CONNECTED_VOICES == ["/app/voice/connected_online.wav"]
    assert module.DISCONNECTED_VOICES == ["/app/voice/disconnected_protocol.wav"]
    assert module.FAILSAFE_VOICES == ["/app/voice/failsafe_intruder.wav"]
    assert module.LOW_VOLTAGE_VOICES == ["/app/voice/low_voltage_retribution.wav"]
    assert module.SOS_VOICES == ["/app/voice/sos_comply.wav"]


def test_config_defaults_sound_mode_to_spectral_voice(
    monkeypatch: pytest.MonkeyPatch,
    config_module,
) -> None:
    monkeypatch.delenv("SOUND_MODE", raising=False)

    module = importlib.reload(config_module)

    assert module.SOUND_MODE == "spectral_voice"


def test_config_accepts_supported_sound_modes(
    monkeypatch: pytest.MonkeyPatch,
    config_module,
) -> None:
    monkeypatch.setenv("SOUND_MODE", "synth")

    module = importlib.reload(config_module)

    assert module.SOUND_MODE == "synth"


def test_config_rejects_invalid_sound_mode(
    monkeypatch: pytest.MonkeyPatch,
    config_module,
) -> None:
    monkeypatch.setenv("SOUND_MODE", "chirp")

    module = importlib.reload(config_module)

    assert module.SOUND_MODE == "spectral_voice"


def test_config_defaults_motor_test_api_settings(
    monkeypatch: pytest.MonkeyPatch,
    config_module,
) -> None:
    monkeypatch.delenv("MOTOR_TEST_API_ENABLED", raising=False)
    monkeypatch.delenv("MOTOR_TEST_API_HOST", raising=False)
    monkeypatch.delenv("MOTOR_TEST_API_PORT", raising=False)

    module = importlib.reload(config_module)

    assert module.MOTOR_TEST_API_ENABLED is True
    assert module.MOTOR_TEST_API_HOST == "0.0.0.0"
    assert module.MOTOR_TEST_API_PORT == 8765


def test_config_applies_motor_test_api_overrides(
    monkeypatch: pytest.MonkeyPatch,
    config_module,
) -> None:
    monkeypatch.setenv("MOTOR_TEST_API_ENABLED", "0")
    monkeypatch.setenv("MOTOR_TEST_API_HOST", "127.0.0.1")
    monkeypatch.setenv("MOTOR_TEST_API_PORT", "9001")

    module = importlib.reload(config_module)

    assert module.MOTOR_TEST_API_ENABLED is False
    assert module.MOTOR_TEST_API_HOST == "127.0.0.1"
    assert module.MOTOR_TEST_API_PORT == 9001


def test_config_applies_environment_overrides(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.setenv("MOTOR1_PWM", "19")
    monkeypatch.setenv("MOTOR_DRIVER_TYPE", "BTS7960")
    monkeypatch.setenv("BTS7960_PWM_MODE", "software")
    monkeypatch.setenv("MOTOR1_INVERTED", "1")
    monkeypatch.setenv("MOTOR2_INVERTED", "1")
    monkeypatch.setenv("LEFT_MOTOR_REN", "26")
    monkeypatch.setenv("RIGHT_MOTOR_LEN", "6")
    monkeypatch.setenv("LEFT_MOTOR_ENABLED", "0")
    monkeypatch.setenv("RIGHT_MOTOR_ENABLED", "0")
    monkeypatch.setenv("THROTTLE_FILTER_MODE", "none")
    monkeypatch.setenv("THROTTLE_KALMAN_PROCESS_NOISE", "0.15")
    monkeypatch.setenv("THROTTLE_KALMAN_MEASUREMENT_NOISE", "0.8")
    monkeypatch.setenv("RAMP_ACCEL_RATE", "1.75")
    monkeypatch.setenv("RAMP_DECEL_RATE", "2.5")
    monkeypatch.setenv("RAMP_REVERSE_DECEL_RATE", "0.5")
    monkeypatch.setenv("FAILSAFE_TIMEOUT_S", "0.75")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("BMS_TRANSPORT", "ble")
    monkeypatch.setenv("BMS_BLE_ADDRESS", "71:C1:46:20:25:4F")
    monkeypatch.setenv("MOTOR_CURRENT_LIMITING_ENABLED", "1")
    monkeypatch.setenv("MOTOR_CURRENT_SENSE_ENABLED", "1")
    monkeypatch.setenv("MOTOR_CURRENT_SENSE_I2C_ADDRESS", "73")
    monkeypatch.setenv("LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL", "3")
    monkeypatch.setenv("LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL", "2")
    monkeypatch.setenv("RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL", "1")
    monkeypatch.setenv("RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL", "0")
    monkeypatch.setenv("MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ", "40")
    monkeypatch.setenv("MOTOR_CURRENT_SENSE_GAIN", "2")
    monkeypatch.setenv("LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V", "0.15")
    monkeypatch.setenv("RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V", "0.25")
    monkeypatch.setenv("LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT", "11.0")
    monkeypatch.setenv("RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT", "12.0")
    monkeypatch.setenv("LEFT_MOTOR_MAX_CURRENT_A", "12.5")
    monkeypatch.setenv("RIGHT_MOTOR_MAX_CURRENT_A", "13.5")
    monkeypatch.setenv("LEFT_MOTOR_MAX_POWER_W", "110")
    monkeypatch.setenv("RIGHT_MOTOR_MAX_POWER_W", "115")
    monkeypatch.setenv("MOTOR_LIMIT_FALLBACK_VOLTAGE", "22.2")
    monkeypatch.setenv("MOTOR_CURRENT_TRACE_ENABLED", "1")
    monkeypatch.setenv("MOTOR_CURRENT_TRACE_PATH", "/tmp/calibration.jsonl")
    monkeypatch.setenv("MOTOR_CURRENT_TRACE_POST_ROLL_S", "3.5")
    monkeypatch.setenv("MOTOR_CURRENT_TRACE_MIN_INTERVAL_S", "0.04")

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 19
    assert module.MOTOR_DRIVER_TYPE == "BTS7960"
    assert module.BTS7960_PWM_MODE == "SOFTWARE"
    assert module.MOTOR1_INVERTED == 1
    assert module.MOTOR2_INVERTED == 1
    assert module.LEFT_MOTOR_REN == 26
    assert module.RIGHT_MOTOR_LEN == 6
    assert module.LEFT_MOTOR_ENABLED is False
    assert module.RIGHT_MOTOR_ENABLED is False
    assert module.THROTTLE_FILTER_MODE == "NONE"
    assert module.THROTTLE_KALMAN_PROCESS_NOISE == pytest.approx(0.15)
    assert module.THROTTLE_KALMAN_MEASUREMENT_NOISE == pytest.approx(0.8)
    assert module.RAMP_ACCEL_RATE == pytest.approx(1.75)
    assert module.RAMP_DECEL_RATE == pytest.approx(2.5)
    assert module.RAMP_REVERSE_DECEL_RATE == pytest.approx(0.5)
    assert module.FAILSAFE_TIMEOUT_S == pytest.approx(0.75)
    assert module.LOG_LEVEL == "DEBUG"
    assert module.BMS_TRANSPORT == "BLE"
    assert module.BMS_BLE_ADDRESS == "71:C1:46:20:25:4F"
    assert module.MOTOR_CURRENT_LIMITING_ENABLED is True
    assert module.MOTOR_CURRENT_SENSE_ENABLED is True
    assert module.MOTOR_CURRENT_SENSE_I2C_ADDRESS == 73
    assert module.LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL == 3
    assert module.LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL == 2
    assert module.RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL == 1
    assert module.RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL == 0
    assert module.MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ == pytest.approx(40.0)
    assert module.MOTOR_CURRENT_SENSE_GAIN == "2"
    assert module.LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V == pytest.approx(0.15)
    assert module.RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V == pytest.approx(0.25)
    assert module.LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT == pytest.approx(11.0)
    assert module.RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT == pytest.approx(12.0)
    assert module.LEFT_MOTOR_MAX_CURRENT_A == pytest.approx(12.5)
    assert module.RIGHT_MOTOR_MAX_CURRENT_A == pytest.approx(13.5)
    assert module.LEFT_MOTOR_MAX_POWER_W == pytest.approx(110.0)
    assert module.RIGHT_MOTOR_MAX_POWER_W == pytest.approx(115.0)
    assert module.MOTOR_LIMIT_FALLBACK_VOLTAGE == pytest.approx(22.2)
    assert module.MOTOR_CURRENT_TRACE_ENABLED is True
    assert module.MOTOR_CURRENT_TRACE_PATH == "/tmp/calibration.jsonl"
    assert module.MOTOR_CURRENT_TRACE_POST_ROLL_S == pytest.approx(3.5)
    assert module.MOTOR_CURRENT_TRACE_MIN_INTERVAL_S == pytest.approx(0.04)


def test_config_ignores_invalid_numeric_environment_values(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.setenv("MOTOR1_PWM", "not-a-number")
    monkeypatch.setenv("MOTOR1_INVERTED", "broken")
    monkeypatch.setenv("FAILSAFE_TIMEOUT_S", "broken")

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 18
    assert module.MOTOR1_INVERTED == 1
    assert module.FAILSAFE_TIMEOUT_S == pytest.approx(0.5)


def test_config_falls_back_to_ble_for_invalid_bms_transport(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.setenv("BMS_TRANSPORT", "zigbee")

    module = importlib.reload(config_module)

    assert module.BMS_TRANSPORT == "BLE"


def test_config_falls_back_to_software_for_invalid_bts7960_pwm_mode(
    monkeypatch: pytest.MonkeyPatch,
    config_module,
) -> None:
    monkeypatch.setenv("BTS7960_PWM_MODE", "ultrasonic")

    module = importlib.reload(config_module)

    assert module.BTS7960_PWM_MODE == "SOFTWARE"


def test_config_defaults_mute_channel_to_ch6(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.delenv("CH_MUTE", raising=False)

    module = importlib.reload(config_module)

    assert module.CH_MUTE == 6


def test_config_defaults_trim_settings(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.delenv("CH_TRIM", raising=False)
    monkeypatch.delenv("MOTOR_TRIM_MAX_EFFECT", raising=False)
    monkeypatch.delenv("MOTOR_TRIM_CONFIRM_HOLD_S", raising=False)
    monkeypatch.delenv("MOTOR_TRIM_SETTINGS_PATH", raising=False)

    module = importlib.reload(config_module)

    assert module.CH_TRIM == 8
    assert module.MOTOR_TRIM_MAX_EFFECT == pytest.approx(0.20)
    assert module.MOTOR_TRIM_CONFIRM_HOLD_S == pytest.approx(5.0)
    assert module.MOTOR_TRIM_SETTINGS_PATH == "/data/motor-trim.json"


def test_docker_compose_exposes_beacon_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "BEACON_ENABLED:" in compose
    assert "BEACON_DELAY_S:" in compose
    assert "CH_BEACON:" in compose
    assert "CH_MUTE:" in compose


def test_env_example_exposes_trim_environment_variables() -> None:
    with open(".env.example", encoding="utf-8") as env_file:
        env_example = env_file.read()

    assert "CH_TRIM=" in env_example
    assert "MOTOR_TRIM_MAX_EFFECT=" in env_example
    assert "MOTOR_TRIM_CONFIRM_HOLD_S=" in env_example
    assert "MOTOR_TRIM_SETTINGS_PATH=" in env_example


def test_docker_compose_exposes_trim_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "CH_TRIM:" in compose
    assert "CH_TRIM: ${CH_TRIM:-8}" in compose
    assert "MOTOR_TRIM_MAX_EFFECT:" in compose
    assert "MOTOR_TRIM_MAX_EFFECT: ${MOTOR_TRIM_MAX_EFFECT:-0.20}" in compose
    assert "MOTOR_TRIM_CONFIRM_HOLD_S:" in compose
    assert "MOTOR_TRIM_CONFIRM_HOLD_S: ${MOTOR_TRIM_CONFIRM_HOLD_S:-5.0}" in compose
    assert "MOTOR_TRIM_SETTINGS_PATH:" in compose
    assert "MOTOR_TRIM_SETTINGS_PATH: ${MOTOR_TRIM_SETTINGS_PATH:-/data/motor-trim.json}" in compose


def test_docker_compose_exposes_bts7960_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "${MOTOR_DRIVER_TYPE:-BTS7960}" in compose
    assert "BTS7960_PWM_MODE:" in compose
    assert "BTS7960_PWM_MODE: ${BTS7960_PWM_MODE:-SOFTWARE}" in compose
    assert "MOTOR_DRIVER_TYPE:" in compose
    assert "${LEFT_MOTOR_LEN:-24}" in compose
    assert "${RIGHT_MOTOR_LPWM:-13}" in compose
    assert "${RIGHT_MOTOR_LEN:-21}" in compose
    assert "LEFT_MOTOR_RPWM:" in compose
    assert "LEFT_MOTOR_LPWM:" in compose
    assert "LEFT_MOTOR_REN:" in compose
    assert "LEFT_MOTOR_LEN:" in compose
    assert "LEFT_MOTOR_ENABLED:" in compose
    assert "RIGHT_MOTOR_RPWM:" in compose
    assert "RIGHT_MOTOR_LPWM:" in compose
    assert "RIGHT_MOTOR_REN:" in compose
    assert "RIGHT_MOTOR_LEN:" in compose
    assert "RIGHT_MOTOR_ENABLED:" in compose
    assert "RIGHT_MOTOR_ENABLED: ${RIGHT_MOTOR_ENABLED:-1}" in compose


def test_docker_compose_exposes_motor_inversion_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "MOTOR1_INVERTED:" in compose
    assert "MOTOR1_INVERTED: ${MOTOR1_INVERTED:-1}" in compose
    assert "MOTOR2_INVERTED:" in compose
    assert "MOTOR2_INVERTED: ${MOTOR2_INVERTED:-0}" in compose


def test_docker_compose_exposes_motor_current_sense_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "MOTOR_CURRENT_LIMITING_ENABLED:" in compose
    assert "MOTOR_CURRENT_LIMITING_ENABLED: ${MOTOR_CURRENT_LIMITING_ENABLED:-0}" in compose
    assert "MOTOR_CURRENT_SENSE_ENABLED:" in compose
    assert "MOTOR_CURRENT_SENSE_ENABLED: ${MOTOR_CURRENT_SENSE_ENABLED:-0}" in compose
    assert "MOTOR_CURRENT_SENSE_I2C_ADDRESS:" in compose
    assert "MOTOR_CURRENT_SENSE_I2C_ADDRESS: ${MOTOR_CURRENT_SENSE_I2C_ADDRESS:-72}" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL:" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL: ${LEFT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL:-2}" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL:" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL: ${LEFT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL:-3}" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL:" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL: ${RIGHT_MOTOR_CURRENT_SENSE_FORWARD_CHANNEL:-0}" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL:" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL: ${RIGHT_MOTOR_CURRENT_SENSE_REVERSE_CHANNEL:-1}" in compose
    assert "MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ:" in compose
    assert "MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ: ${MOTOR_CURRENT_SENSE_SAMPLE_RATE_HZ:-32}" in compose
    assert "MOTOR_CURRENT_SENSE_GAIN:" in compose
    assert "MOTOR_CURRENT_SENSE_GAIN: ${MOTOR_CURRENT_SENSE_GAIN:-1}" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V:" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V: ${LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V:-0.0}" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V:" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V: ${RIGHT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V:-0.0}" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT:" in compose
    assert "LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT: ${LEFT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT:-1.0}" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT:" in compose
    assert "RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT: ${RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT:-1.0}" in compose


def test_docker_compose_exposes_ble_bms_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "BMS_TRANSPORT:" in compose
    assert "BMS_TRANSPORT: ${BMS_TRANSPORT:-BLE}" in compose
    assert "BMS_BLE_ADDRESS:" in compose
    assert "BMS_BLE_SERVICE_UUID:" in compose
    assert "BMS_BLE_WRITE_UUID:" in compose
    assert "BMS_BLE_NOTIFY_UUID:" in compose


def test_docker_compose_exposes_pigpio_device_mappings() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "/dev/gpiomem:/dev/gpiomem" in compose
    assert "/dev/vcio:/dev/vcio" in compose
    assert "/dev/mem:/dev/mem" in compose


def test_env_example_documents_beacon_environment_variables() -> None:
    with open(".env.example", encoding="utf-8") as env_file:
        env_example = env_file.read()

    assert "BMS_TRANSPORT=BLE" in env_example
    assert "BEACON_ENABLED=" in env_example
    assert "BEACON_DELAY_S=" in env_example
    assert "CH_BEACON=" in env_example
    assert "CH_MUTE=" in env_example
    assert "MOTOR_DRIVER_TYPE=BTS7960" in env_example
    assert "BTS7960_PWM_MODE=SOFTWARE" in env_example
    assert "THROTTLE_FILTER_MODE=NONE" in env_example
    assert "THROTTLE_KALMAN_PROCESS_NOISE=0.02" in env_example
    assert "THROTTLE_KALMAN_MEASUREMENT_NOISE=0.5" in env_example
    assert "RAMP_ZERO_HOLD_S=0.15" in env_example
    assert "RAMP_ACCEL_RATE=2.0" in env_example
    assert "RAMP_DECEL_RATE=0.5" in env_example
    assert "RAMP_REVERSE_DECEL_RATE=0.5" in env_example
    assert "LEFT_MOTOR_RPWM=" in env_example
    assert "LEFT_MOTOR_LEN=24" in env_example
    assert "LEFT_MOTOR_ENABLED=1" in env_example
    assert "RIGHT_MOTOR_LPWM=13" in env_example
    assert "RIGHT_MOTOR_REN=20" in env_example
    assert "RIGHT_MOTOR_LEN=21" in env_example
    assert "RIGHT_MOTOR_ENABLED=1" in env_example
    assert "MOTOR1_INVERTED=1" in env_example
    assert "MOTOR2_INVERTED=0" in env_example
    assert "MOTOR_CURRENT_LIMITING_ENABLED=" in env_example
    assert "MOTOR_CURRENT_SENSE_ENABLED=" in env_example
    assert "MOTOR_CURRENT_SENSE_I2C_ADDRESS=" in env_example
    assert "MOTOR_CURRENT_SENSE_GAIN=" in env_example
    assert "LEFT_MOTOR_CURRENT_SENSE_ZERO_OFFSET_V=" in env_example
    assert "RIGHT_MOTOR_CURRENT_SENSE_AMPS_PER_VOLT=" in env_example
    assert "LEFT_MOTOR_MAX_CURRENT_A=" in env_example
    assert "RIGHT_MOTOR_MAX_POWER_W=" in env_example
    assert "MOTOR_CURRENT_TRACE_ENABLED=" in env_example
    assert "MOTOR_CURRENT_TRACE_PATH=" in env_example
    assert "MOTOR_CURRENT_TRACE_POST_ROLL_S=" in env_example
    assert "MOTOR_CURRENT_TRACE_MIN_INTERVAL_S=" in env_example



def test_docker_compose_uses_matching_default_ramp_rates() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "RAMP_ACCEL_RATE: ${RAMP_ACCEL_RATE:-2.0}" in compose
    assert "RAMP_DECEL_RATE: ${RAMP_DECEL_RATE:-0.5}" in compose
    assert "RAMP_REVERSE_DECEL_RATE: ${RAMP_REVERSE_DECEL_RATE:-0.5}" in compose


def test_docker_compose_exposes_current_trace_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "MOTOR_CURRENT_TRACE_ENABLED:" in compose
    assert "MOTOR_CURRENT_TRACE_ENABLED: ${MOTOR_CURRENT_TRACE_ENABLED:-0}" in compose
    assert "MOTOR_CURRENT_TRACE_PATH:" in compose
    assert "MOTOR_CURRENT_TRACE_PATH: ${MOTOR_CURRENT_TRACE_PATH:-/data/current-trace.jsonl}" in compose
    assert "MOTOR_CURRENT_TRACE_POST_ROLL_S:" in compose
    assert "MOTOR_CURRENT_TRACE_POST_ROLL_S: ${MOTOR_CURRENT_TRACE_POST_ROLL_S:-2.0}" in compose
    assert "MOTOR_CURRENT_TRACE_MIN_INTERVAL_S:" in compose
    assert "MOTOR_CURRENT_TRACE_MIN_INTERVAL_S: ${MOTOR_CURRENT_TRACE_MIN_INTERVAL_S:-0.0}" in compose


def test_docker_compose_exposes_throttle_filter_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "THROTTLE_FILTER_MODE:" in compose
    assert "THROTTLE_KALMAN_PROCESS_NOISE:" in compose
    assert "THROTTLE_KALMAN_MEASUREMENT_NOISE:" in compose
    assert "RAMP_ZERO_HOLD_S:" in compose