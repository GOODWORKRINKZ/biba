# Phase 06: IS-Signal RPM Proof-of-Concept — Summary

**Статус:** COMPLETE  
**Закрыта:** 2026-05-23

## Что было сделано

1. **Отдельный PlatformIO env** `rpico_rp2040_is_poc` — USB CDC shell с командами PING / STOP / CAPTURE / SWEEP / SWEEPRAW / STEPRUN / RPMTRACK
2. **DMA-захват IS-сигнала** через GP26 (IS_LEFT, RC-фильтр 1kΩ‖1kΩ + 0.1µF, f_c ≈ 3.2 kHz), 1024 сэмпла @ 10 kSPS = 100 мс окно
3. **Три алгоритма оценки частоты** реализованы и протестированы: FFT peak, autocorrelation, zero-crossing (Schmitt)
4. **A2 Sub-window Schmitt ZC** выбран как лучший — 8 блоков × 128 сэмплов, локальный гистерезис per-block, устойчив к шуму
5. **Калибровка растения**: K = 10.13 Hz/%, dead_zone = 74.6 Hz, R² > 0.95
6. **PI-регулятор скорости** с FF, integral clamping, stiction floor, transient blanking — bidirectional [-1, 1]
7. **Python toolchain**: `is_poc_capture.py`, `is_poc_analyse.py`, `is_poc_step.py`, `is_poc_rpmtrack.py`, `is_step_response_analysis.py`, `is_trap_step_extractor.py`

## Ключевые метрики

| Метрика | Значение |
|---------|---------|
| Линейность IS → Hz | R² > 0.95 |
| Точность ZC (синтетика) | ±5% @ 180–940 Hz |
| Step response rise (TRAP) | ~400 ms |
| Step response OS (TRAP) | ~7% |
| Settle time (forward) | ~1140 ms |
| SS error | < 2% |

## Выводы для Phase 07

- Переносить **A2 Sub-window Schmitt ZC** (не FFT/autocorr — дорого для embedded)
- Добавить **gain scheduling** или кусочно-линейный FF для duty < 25% (большой OS при малых RPM)
- Поле `wheel_rpm_hz × 10` в STM32-link proto
- HAL уже поддерживает bidirectional — дополнительный слой не нужен
