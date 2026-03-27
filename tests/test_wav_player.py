"""Tests for WAV file loading and PCM-over-PWM audio playback."""

from __future__ import annotations

import io
import struct
import threading
import wave

from unittest.mock import MagicMock, call, patch

import pytest

from buzzer.wav_player import (
    DEFAULT_CARRIER_HZ,
    _fft,
    _next_pow2,
    _SPECTRAL_DUTY_MAX,
    _SPECTRAL_FRAME_MS,
    _SPECTRAL_HOP_MS,
    _SPEECH_MAX_FREQ,
    _SPEECH_MIN_FREQ,
    _stabilize_peak_frames,
    load_wav,
    play_peak_frames,
    play_samples,
    play_tone_sequence,
    wav_to_peak_frames,
    wav_to_tones,
)


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
        pins = [18]
        samples = bytes([0, 128, 255])
        stop = threading.Event()

        play_samples(pi, pins, samples, sample_rate=8000,
                     carrier_freq=25000, interrupt_event=stop)

        calls = pi.hardware_PWM.call_args_list

        # At minimum, first sample is always played + cleanup
        assert len(calls) >= 2
        # First sample (0) on pin 18
        assert calls[0] == call(18, 25000, 0)
        # Cleanup last
        assert calls[-1] == call(18, 0, 0)

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

    def test_default_carrier_frequency_is_4khz(self):
        assert DEFAULT_CARRIER_HZ == 4000

    def test_comp_pins_receive_complementary_duty(self):
        pi = MagicMock()
        pins = [18]
        comp_pins = [13]
        # Sample 255 → duty 1_000_000, comp duty 0
        samples = bytes([255])
        stop = threading.Event()

        play_samples(pi, pins, samples, sample_rate=8000,
                     carrier_freq=25000, interrupt_event=stop,
                     comp_pins=comp_pins)

        calls = pi.hardware_PWM.call_args_list
        # First: pin 18 gets full duty
        assert call(18, 25000, 1_000_000) in calls
        # Complementary pin 13 gets zero duty
        assert call(13, 25000, 0) in calls
        # Cleanup for both
        assert call(18, 0, 0) in calls
        assert call(13, 0, 0) in calls

    def test_comp_pins_cleanup_on_empty_samples(self):
        pi = MagicMock()
        pins = [18]
        comp_pins = [13]
        samples = bytes()
        stop = threading.Event()

        play_samples(pi, pins, samples, sample_rate=8000,
                     carrier_freq=25000, interrupt_event=stop,
                     comp_pins=comp_pins)

        assert call(18, 0, 0) in pi.hardware_PWM.call_args_list
        assert call(13, 0, 0) in pi.hardware_PWM.call_args_list


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


# ---------------------------------------------------------------------------
# FFT helper tests
# ---------------------------------------------------------------------------

class TestFFT:
    def test_next_pow2(self):
        assert _next_pow2(1) == 1
        assert _next_pow2(3) == 4
        assert _next_pow2(120) == 128
        assert _next_pow2(256) == 256

    def test_fft_single_element(self):
        result = _fft([complex(5.0)])
        assert len(result) == 1
        assert abs(result[0] - 5.0) < 1e-9

    def test_fft_dc_signal(self):
        # All-ones → DC bin has amplitude N, all others zero
        n = 8
        result = _fft([complex(1.0)] * n)
        assert abs(result[0] - n) < 1e-9
        for k in range(1, n):
            assert abs(result[k]) < 1e-9

    def test_fft_pure_tone_peak_at_correct_bin(self):
        import cmath
        n = 64
        freq_bin = 8  # 8 cycles in 64 samples
        signal = [cmath.exp(2j * cmath.pi * freq_bin * i / n) for i in range(n)]
        result = _fft(signal)
        magnitudes = [abs(result[k]) for k in range(n)]
        peak = magnitudes.index(max(magnitudes))
        assert peak == freq_bin


# ---------------------------------------------------------------------------
# wav_to_tones tests
# ---------------------------------------------------------------------------

class TestWavToTones:
    def test_returns_tone_tuples(self, tmp_path):
        # 400 samples of a 1kHz sine at 8kHz → 50ms → several frames
        import math
        n = 400
        samples = [int(32767 * math.sin(2 * math.pi * 1000 * i / 8000)) for i in range(n)]
        wav_path = tmp_path / "tone.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        tones = wav_to_tones(str(wav_path), frame_ms=20)

        assert len(tones) > 0
        for freq, duty, dur in tones:
            assert isinstance(freq, int)
            assert isinstance(duty, int)
            assert dur == 20
            assert 0 <= duty <= _SPECTRAL_DUTY_MAX

    def test_detects_frequency_of_pure_tone(self, tmp_path):
        import math
        n = 800  # 100ms at 8kHz
        target_freq = 500
        samples = [int(32767 * math.sin(2 * math.pi * target_freq * i / 8000)) for i in range(n)]
        wav_path = tmp_path / "tone.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        tones = wav_to_tones(str(wav_path), frame_ms=20)

        # All voiced frames should detect ~500 Hz (within FFT bin resolution)
        voiced = [f for f, d, _ in tones if f > 0]
        assert len(voiced) > 0
        for f in voiced:
            assert abs(f - target_freq) < 100  # within ~100 Hz tolerance

    def test_silence_produces_zero_freq(self, tmp_path):
        samples = [0] * 400
        wav_path = tmp_path / "silence.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        tones = wav_to_tones(str(wav_path), frame_ms=20)

        for freq, duty, _ in tones:
            assert freq == 0
            assert duty == 0

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            wav_to_tones("/nonexistent/path.wav")


class TestWavToPeakFrames:
    def test_detects_multiple_peaks_in_same_frame(self, tmp_path):
        import math

        n = 800
        samples = [
            int(
                16000 * math.sin(2 * math.pi * 300 * i / 8000)
                + 12000 * math.sin(2 * math.pi * 700 * i / 8000)
            )
            for i in range(n)
        ]
        wav_path = tmp_path / "dual-tone.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        frames = wav_to_peak_frames(str(wav_path), frame_ms=10, hop_ms=5, n_peaks=2, max_freq=800)

        voiced = [peaks for peaks, duration in frames if peaks]
        assert voiced
        peak_freqs = [freq for freq, _duty in voiced[0]]
        assert len(peak_freqs) >= 2
        assert any(abs(freq - 300) < 120 for freq in peak_freqs)
        assert any(abs(freq - 700) < 180 for freq in peak_freqs)

    def test_overlap_increases_frame_count(self, tmp_path):
        import math

        n = 1600
        samples = [int(32767 * math.sin(2 * math.pi * 700 * i / 8000)) for i in range(n)]
        wav_path = tmp_path / "tone.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        without_overlap = wav_to_peak_frames(str(wav_path), frame_ms=10, hop_ms=10, n_peaks=2)
        with_overlap = wav_to_peak_frames(str(wav_path), frame_ms=10, hop_ms=5, n_peaks=2)

        assert len(with_overlap) > len(without_overlap)

    def test_default_analysis_limits_frames_to_two_peaks(self, tmp_path):
        import math

        n = 800
        samples = [
            int(
                12000 * math.sin(2 * math.pi * 350 * i / 8000)
                + 9000 * math.sin(2 * math.pi * 800 * i / 8000)
                + 7000 * math.sin(2 * math.pi * 1400 * i / 8000)
            )
            for i in range(n)
        ]
        wav_path = tmp_path / "triple-tone.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        frames = wav_to_peak_frames(str(wav_path))

        voiced = [peaks for peaks, _duration in frames if peaks]
        assert voiced
        assert all(len(peaks) <= 2 for peaks in voiced)

    def test_default_analysis_filters_peaks_above_speech_band(self, tmp_path):
        import math

        n = 800
        samples = [
            int(
                16000 * math.sin(2 * math.pi * 600 * i / 8000)
                + 16000 * math.sin(2 * math.pi * 2200 * i / 8000)
            )
            for i in range(n)
        ]
        wav_path = tmp_path / "band-limited.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        frames = wav_to_peak_frames(str(wav_path))

        voiced = [peaks for peaks, _duration in frames if peaks]
        assert voiced
        peak_freqs = [freq for freq, _duty in voiced[0]]
        assert any(abs(freq - 600) < 120 for freq in peak_freqs)
        assert all(abs(freq - 2200) >= 180 for freq in peak_freqs)

    def test_duty_tracks_frame_rms_envelope(self, tmp_path):
        import math

        loud = [int(28000 * math.sin(2 * math.pi * 500 * i / 8000)) for i in range(160)]
        quiet = [int(6000 * math.sin(2 * math.pi * 500 * i / 8000)) for i in range(160)]
        wav_path = tmp_path / "envelope.wav"
        wav_path.write_bytes(_make_wav(samples=loud + quiet, sample_rate=8000))

        frames = wav_to_peak_frames(
            str(wav_path),
            frame_ms=20,
            hop_ms=20,
            n_peaks=1,
            max_freq=1800,
        )

        voiced = [peaks for peaks, _duration in frames if peaks]
        assert len(voiced) >= 2
        loud_duty = voiced[0][0][1]
        quiet_duty = voiced[1][0][1]
        assert loud_duty > quiet_duty

    def test_default_constants_match_espeak_band(self):
        """Constants should be narrowed to the eSpeak speech content range."""
        assert _SPEECH_MIN_FREQ >= 150
        assert _SPEECH_MAX_FREQ <= 800
        assert _SPECTRAL_FRAME_MS <= 12
        assert _SPECTRAL_HOP_MS <= 6

    def test_default_analysis_rejects_low_frequency_hum(self, tmp_path):
        """A 80 Hz tone (below speech band) should not appear in default peaks."""
        import math

        n = 800
        samples = [
            int(
                16000 * math.sin(2 * math.pi * 80 * i / 8000)
                + 12000 * math.sin(2 * math.pi * 400 * i / 8000)
            )
            for i in range(n)
        ]
        wav_path = tmp_path / "low-hum.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        frames = wav_to_peak_frames(str(wav_path))

        voiced = [peaks for peaks, _duration in frames if peaks]
        assert voiced
        for peaks in voiced:
            for freq, _duty in peaks:
                assert freq >= 120, f"Low hum {freq} Hz leaked through"

    def test_default_analysis_rejects_high_frequency_noise(self, tmp_path):
        """A 1200 Hz tone (above narrowed speech band) should be excluded."""
        import math

        n = 800
        samples = [
            int(
                16000 * math.sin(2 * math.pi * 400 * i / 8000)
                + 16000 * math.sin(2 * math.pi * 1200 * i / 8000)
            )
            for i in range(n)
        ]
        wav_path = tmp_path / "high-noise.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        frames = wav_to_peak_frames(str(wav_path))

        voiced = [peaks for peaks, _duration in frames if peaks]
        assert voiced
        peak_freqs = [freq for freq, _duty in voiced[0]]
        assert any(abs(freq - 400) < 100 for freq in peak_freqs)
        assert all(freq < 850 for freq in peak_freqs), f"High freq leaked: {peak_freqs}"

    def test_shorter_frames_produce_more_temporal_detail(self, tmp_path):
        """With frame_ms=12 and hop_ms=6, we should get more frames than 18/9."""
        import math

        n = 1600
        samples = [int(32767 * math.sin(2 * math.pi * 400 * i / 8000)) for i in range(n)]
        wav_path = tmp_path / "tone.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))

        frames_old = wav_to_peak_frames(str(wav_path), frame_ms=18, hop_ms=9)
        frames_new = wav_to_peak_frames(str(wav_path))  # should use 12/6 now

        assert len(frames_new) > len(frames_old), (
            f"Default frames ({len(frames_new)}) should be more than 18/9 ({len(frames_old)})"
        )


class TestStabilizePeakFrames:
    def test_snaps_nearby_frequency_to_previous_frame(self):
        frames = [
            ([(1000, 200000)], 5),
            ([(1060, 210000)], 5),
        ]

        stabilized = _stabilize_peak_frames(frames, freq_snap_hz=80, duty_blend=0.5)

        assert stabilized[0][0][0][0] == 1000
        assert stabilized[1][0][0][0] == 1000

    def test_smooths_duty_between_frames(self):
        frames = [
            ([(1000, 100000)], 5),
            ([(1030, 300000)], 5),
        ]

        stabilized = _stabilize_peak_frames(frames, freq_snap_hz=80, duty_blend=0.25)

        assert stabilized[1][0][0][0] == 1000
        assert stabilized[1][0][0][1] == 150000


# ---------------------------------------------------------------------------
# play_tone_sequence tests
# ---------------------------------------------------------------------------

class TestPlayToneSequence:
    def test_plays_tones_and_cleans_up(self):
        pi = MagicMock()
        pins = [18, 13]
        tones = [(440, 200000, 10)]

        with patch("buzzer.wav_player.time.sleep"):
            play_tone_sequence(pi, pins, tones)

        # Should have set freq on both pins, then cleanup
        calls = pi.hardware_PWM.call_args_list
        assert call(18, 440, 200000) in calls
        assert call(13, 440, 200000) in calls
        # Cleanup at end
        assert calls[-1] == call(13, 0, 0) or calls[-2] == call(13, 0, 0)

    def test_silence_frame_turns_off_pins(self):
        pi = MagicMock()
        pins = [18]
        tones = [(0, 0, 10)]

        with patch("buzzer.wav_player.time.sleep"):
            play_tone_sequence(pi, pins, tones)

        # All calls should be (pin, 0, 0)
        for c in pi.hardware_PWM.call_args_list:
            assert c == call(18, 0, 0)

    def test_interrupt_stops_early(self):
        pi = MagicMock()
        pins = [18]
        tones = [(440, 200000, 10)] * 100
        stop = threading.Event()
        stop.set()

        play_tone_sequence(pi, pins, tones, interrupt_event=stop)

        # Should barely play any tones
        # Just cleanup calls
        assert pi.hardware_PWM.call_count <= 2

    def test_empty_tones_just_cleans_up(self):
        pi = MagicMock()
        pins = [18, 13]

        play_tone_sequence(pi, pins, [])

        assert call(18, 0, 0) in pi.hardware_PWM.call_args_list
        assert call(13, 0, 0) in pi.hardware_PWM.call_args_list


class TestPlayPeakFrames:
    def test_plays_multiple_peaks_within_frame(self):
        pi = MagicMock()
        pins = [18]
        frames = [([(500, 120000), (900, 80000)], 10)]

        with patch("buzzer.wav_player.time.sleep"):
            play_peak_frames(pi, pins, frames)

        calls = pi.hardware_PWM.call_args_list
        assert call(18, 500, 120000) in calls
        assert call(18, 900, 80000) in calls
        assert call(18, 0, 0) in calls


# ---------------------------------------------------------------------------
# MotorSynth.play_spectral integration tests
# ---------------------------------------------------------------------------

class TestMotorSynthPlaySpectral:
    def _make_synth(self):
        pi = MagicMock()
        from buzzer.motor_synth import MotorSynth
        synth = MotorSynth(pi, [18, 13])
        return synth, pi

    def test_play_spectral_calls_hardware_pwm(self, tmp_path):
        synth, pi = self._make_synth()
        import math
        samples = [int(32767 * math.sin(2 * math.pi * 500 * i / 8000)) for i in range(400)]
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))
        pi.hardware_PWM.reset_mock()

        with patch("buzzer.wav_player.time.sleep"):
            synth.play_spectral(str(wav_path))

        assert pi.hardware_PWM.called

    def test_play_spectral_default_path_emits_multiple_voiced_frequencies(self, tmp_path):
        synth, pi = self._make_synth()
        import math

        samples = [
            int(
                14000 * math.sin(2 * math.pi * 300 * i / 8000)
                + 12000 * math.sin(2 * math.pi * 700 * i / 8000)
            )
            for i in range(800)
        ]
        wav_path = tmp_path / "dual-tone-defaults.wav"
        wav_path.write_bytes(_make_wav(samples=samples, sample_rate=8000))
        pi.hardware_PWM.reset_mock()

        with patch("buzzer.wav_player.time.sleep"):
            synth.play_spectral(str(wav_path))

        voiced_frequencies = {
            freq
            for _pin, freq, duty in (call.args for call in pi.hardware_PWM.call_args_list)
            if freq > 0 and duty > 0
        }

        assert len(voiced_frequencies) >= 2
        assert any(abs(freq - 300) < 120 for freq in voiced_frequencies)
        assert any(abs(freq - 700) < 180 for freq in voiced_frequencies)

    def test_play_spectral_respects_control_active(self, tmp_path):
        synth, pi = self._make_synth()
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(_make_wav(samples=[0, 32767], sample_rate=8000))

        synth.set_control_active(True)
        pi.hardware_PWM.reset_mock()

        synth.play_spectral(str(wav_path))

        pi.hardware_PWM.assert_not_called()

    def test_play_spectral_missing_file_logs_not_crashes(self):
        synth, _ = self._make_synth()
        synth.play_spectral("/nonexistent/startup.wav")
