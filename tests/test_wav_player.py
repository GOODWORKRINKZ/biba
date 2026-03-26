"""Tests for WAV file loading and PCM-over-PWM audio playback."""

from __future__ import annotations

import io
import struct
import threading
import wave

from unittest.mock import MagicMock, call

import pytest

from buzzer.wav_player import load_wav, play_samples, DEFAULT_CARRIER_HZ


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav(
    *,
    sample_rate: int = 8000,
    n_channels: int = 1,
    sampwidth: int = 2,
    samples: list[int] | None = None,
) -> bytes:
    """Create a minimal in-memory WAV file and return its bytes."""
    if samples is None:
        # Simple ramp 0..255 as 16-bit signed: map 0..255 → -32768..32512
        samples = [int((i / 255) * 65535 - 32768) for i in range(256)]

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        if sampwidth == 2:
            raw = b"".join(struct.pack("<h", s) for s in samples)
        else:
            # 8-bit unsigned
            raw = bytes(s & 0xFF for s in samples)
        if n_channels == 2 and sampwidth == 2:
            # interleaved stereo: duplicate each sample
            raw = b"".join(
                struct.pack("<hh", s, s) for s in samples
            )
        elif n_channels == 2 and sampwidth == 1:
            raw = b"".join(bytes([s & 0xFF, s & 0xFF]) for s in samples)
        wf.writeframes(raw)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# load_wav tests
# ---------------------------------------------------------------------------

class TestLoadWav:
    def test_loads_16bit_mono_wav(self, tmp_path):
        wav_path = tmp_path / "test.wav"
        # 4 samples: silence, quarter, half, full
        samples_16 = [-32768, -16384, 0, 32767]
        wav_path.write_bytes(_make_wav(samples=samples_16))

        samples, rate = load_wav(str(wav_path))

        assert rate == 8000
        assert len(samples) == 4
        # 16-bit signed → 8-bit unsigned: (sample + 32768) >> 8
        # -32768 → 0, -16384 → 64, 0 → 128, 32767 → 255
        assert samples[0] == 0
        assert samples[1] == 64
        assert samples[2] == 128
        assert samples[3] == 255

    def test_loads_8bit_mono_wav(self, tmp_path):
        wav_path = tmp_path / "test.wav"
        # 8-bit WAV samples are unsigned 0-255
        raw_samples = [0, 64, 128, 255]
        wav_path.write_bytes(_make_wav(
            samples=raw_samples,
            sampwidth=1,
        ))

        samples, rate = load_wav(str(wav_path))

        assert rate == 8000
        assert len(samples) == 4
        assert list(samples) == [0, 64, 128, 255]

    def test_loads_stereo_downmixes_to_mono(self, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav(
            samples=[-32768, 0, 32767],
            n_channels=2,
        ))

        samples, rate = load_wav(str(wav_path))

        # Stereo is mixed to mono — we have 3 frames
        assert len(samples) == 3

    def test_preserves_sample_rate(self, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav(sample_rate=22050, samples=[0, 0]))

        _samples, rate = load_wav(str(wav_path))

        assert rate == 22050

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_wav("/nonexistent/path.wav")


# ---------------------------------------------------------------------------
# play_samples tests
# ---------------------------------------------------------------------------

class TestPlaySamples:
    def test_sets_carrier_and_duty_per_sample(self):
        pi = MagicMock()
        pins = [18, 13]
        samples = bytes([0, 128, 255])
        stop = threading.Event()

        play_samples(pi, pins, samples, sample_rate=8000,
                     carrier_freq=25000, interrupt_event=stop)

        # Each sample → hardware_PWM on each pin
        # sample 0   → duty 0
        # sample 128 → duty ~502000  (128 * 1_000_000 // 255)
        # sample 255 → duty 1_000_000
        calls = pi.hardware_PWM.call_args_list

        # 3 samples × 2 pins = 6 calls + 2 cleanup calls (off)
        assert len(calls) >= 6

        # First sample (0) on pin 18
        assert call(18, 25000, 0) in calls
        # Last sample (255) on pin 18
        assert call(18, 25000, 1_000_000) in calls
        # Middle sample (128) on pin 13
        expected_duty_128 = 128 * 1_000_000 // 255
        assert call(13, 25000, expected_duty_128) in calls

    def test_cleans_up_pins_after_playback(self):
        pi = MagicMock()
        pins = [18, 13]
        samples = bytes([128])
        stop = threading.Event()

        play_samples(pi, pins, samples, sample_rate=8000,
                     carrier_freq=25000, interrupt_event=stop)

        # Last calls should be cleanup: (pin, 0, 0) for each pin
        last_calls = pi.hardware_PWM.call_args_list[-2:]
        assert call(18, 0, 0) in last_calls
        assert call(13, 0, 0) in last_calls

    def test_interrupt_stops_playback_early(self):
        pi = MagicMock()
        pins = [18]
        # Long sample buffer
        samples = bytes([128] * 10000)
        stop = threading.Event()

        original_hw_pwm = pi.hardware_PWM

        def counting_hwpwm(*args):
            original_hw_pwm(*args)
            if pi.hardware_PWM.call_count > 50:
                stop.set()

        pi.hardware_PWM = MagicMock(side_effect=counting_hwpwm)

        play_samples(pi, pins, samples, sample_rate=8000,
                     carrier_freq=25000, interrupt_event=stop)

        # Should have stopped well before playing all 10000 samples
        assert pi.hardware_PWM.call_count < 10000

    def test_empty_samples_just_cleans_up(self):
        pi = MagicMock()
        pins = [18, 13]
        samples = bytes()
        stop = threading.Event()

        play_samples(pi, pins, samples, sample_rate=8000,
                     carrier_freq=25000, interrupt_event=stop)

        # Should just do cleanup
        assert call(18, 0, 0) in pi.hardware_PWM.call_args_list
        assert call(13, 0, 0) in pi.hardware_PWM.call_args_list

    def test_default_carrier_frequency_is_25khz(self):
        assert DEFAULT_CARRIER_HZ == 25000


# ---------------------------------------------------------------------------
# MotorSynth.play_wav integration tests
# ---------------------------------------------------------------------------

class TestMotorSynthPlayWav:
    def _make_synth(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth
        synth = MotorSynth(pi, [18, 13])
        return synth, pi

    def test_play_wav_calls_hardware_pwm(self, tmp_path):
        synth, pi = self._make_synth()
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav(samples=[0, 32767], sample_rate=8000))
        pi.hardware_PWM.reset_mock()

        synth.play_wav(str(wav_path))

        assert pi.hardware_PWM.called

    def test_play_wav_respects_control_active(self, tmp_path):
        synth, pi = self._make_synth()
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav(samples=[0, 32767], sample_rate=8000))

        synth.set_control_active(True)
        pi.hardware_PWM.reset_mock()

        synth.play_wav(str(wav_path))

        # No new calls except cleanup — play_wav should bail early
        pi.hardware_PWM.assert_not_called()

    def test_play_wav_missing_file_logs_not_crashes(self, tmp_path):
        synth, pi = self._make_synth()

        # Should not raise
        synth.play_wav("/nonexistent/startup.wav")

    def test_play_wav_async_runs_in_thread(self, tmp_path):
        synth, pi = self._make_synth()
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav(samples=[0], sample_rate=8000))

        t = synth.play_wav_async(str(wav_path))
        t.join(timeout=2.0)

        assert not t.is_alive()
