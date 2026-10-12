#!/usr/bin/env python3
"""Характеристика IS-сигнала (коммутационные пульсации тока BTS7960) по сырым записям.

Нужно, чтобы выбирать аппаратный фронтенд (компаратор/F-V/сопроцессор) не вслепую:
уровень DC, амплитуда пульсаций, SNR, полезная полоса, поведение при смене газа.

Вход: `scripts/artifacts/is-sweepraw/sweepraw_SIN_amp100_per8000_n157_*_fullsine_{left,right}.csv`
(синусная развёртка duty ±100 %, период 8 с, окна по 1024 отсчёта @ 10 kSPS).
Выход: таблицы в stdout + `scripts/artifacts/is_signal_characterization.png`
и `scripts/artifacts/is_signal_timedomain.png`.

Только numpy + matplotlib (без pandas), запуск: `python scripts/is_signal_characterize.py`.
"""
import collections
import csv
import glob
import os
import sys

import numpy as np

FS = 10_000
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts")
PLANT_K, PLANT_DEAD = 10.13, 74.6          # f_hz = K·|duty| − dead (фаза 06)


def load(path):
    wins = collections.OrderedDict()
    with open(path, newline="") as fh:
        rd = csv.reader(fh)
        next(rd)
        for w, t, duty, _i, a in rd:
            wins.setdefault(int(w), [float(t), float(duty), []])[2].append(float(a))
    return wins


def win_stats(x):
    x = np.asarray(x, float)
    n = len(x)
    dc = x.mean()
    ac = x - dc
    spec = np.abs(np.fft.rfft(ac * np.hanning(n)))
    fr = np.fft.rfftfreq(n, 1 / FS)
    band = (fr > 60) & (fr < 2500)
    k = int(np.argmax(spec * band))
    return dict(dc=dc, acrms=ac.std(), p2p=np.ptp(x), fpk=fr[k],
                snr=spec[k] / np.median(spec[band]),
                drift=x[n // 2:].mean() - x[: n // 2].mean())


def analyse(path):
    rows = []
    prev = None
    for w, (t, duty, x) in load(path).items():
        s = win_stats(x)
        s.update(w=w, t=t / 1000, duty=duty, n=len(x),
                 fexp=max(0.0, PLANT_K * abs(duty) - PLANT_DEAD),
                 slew=0.0 if prev is None else (duty - prev[1]) / ((t - prev[0]) / 1000))
        prev = (t, duty)
        rows.append(s)
    return rows


def col(rows, key):
    return np.array([r[key] for r in rows])


def report(side, rows):
    print(f"=== {side}: {len(rows)} окон × {rows[0]['n']} отсчётов ({rows[0]['n'] / FS * 1000:.0f} мс)")
    print(f"{'|duty|':>7} {'n':>3} {'DC cnt':>7} {'DC V':>5} {'ACrms':>6} {'p2p':>5} {'fpk':>5} {'fexp':>5} {'SNR':>6} {'SNRmin':>6}")
    for lo, hi in [(0, 5), (5, 15), (15, 25), (25, 40), (40, 60), (60, 80), (80, 101)]:
        g = [r for r in rows if lo <= abs(r["duty"]) < hi]
        if not g:
            continue
        m = lambda k, f=np.median: f([r[k] for r in g])
        print(f"{lo:>3}-{hi:<3} {len(g):>3} {m('dc'):7.0f} {m('dc') * 3.3 / 4095:5.2f} {m('acrms'):6.1f} "
              f"{m('p2p'):5.0f} {m('fpk'):5.0f} {m('fexp'):5.0f} {m('snr'):6.1f} {m('snr', np.min):6.1f}")
    D, SL, DR, A, F, S = (col(rows, k) for k in ("duty", "slew", "drift", "acrms", "fpk", "snr"))
    fexp = col(rows, "fexp")
    print("-- смена газа: окна по |d duty/dt|")
    for lo, hi in [(0, 10), (10, 30), (30, 60), (60, 200)]:
        m = (np.abs(SL) >= lo) & (np.abs(SL) < hi) & (np.abs(D) > 15)
        if not m.any():
            continue
        print(f"  {lo:>3}-{hi:<3} %/с: окон {m.sum():3d}, |ΔDC| внутри окна медиана {np.median(np.abs(DR[m])):5.1f} "
              f"(макс {np.abs(DR[m]).max():4.0f}) cnt, ACrms {np.median(A[m]):5.1f} cnt, SNR медиана {np.median(S[m]):6.1f}")
    acc = (SL * np.sign(D) > 30) & (np.abs(D) > 20)
    dec = (SL * np.sign(D) < -30) & (np.abs(D) > 20)
    if acc.any() and dec.any():
        print(f"  разгон: fpk/fexp медиана {np.median(F[acc] / np.maximum(fexp[acc], 1)):.2f}; "
              f"сброс газа: {np.median(F[dec] / np.maximum(fexp[dec], 1)):.2f} (колесо отстаёт от duty)")
    ok = S > 8
    print(f"  SNR>8: при |duty|>=20 % — {100 * ok[np.abs(D) >= 20].mean():.0f} % окон, при |duty|<20 % — "
          f"{100 * ok[np.abs(D) < 20].mean():.0f} %")


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    files = {}
    for side in ("right", "left"):
        hits = sorted(glob.glob(os.path.join(ART, "is-sweepraw", f"sweepraw_SIN_amp100_per8000_*fullsine_{side}.csv")))
        if hits:
            files[side] = hits[-1]
    if not files:
        print("нет fullsine-записей в scripts/artifacts/is-sweepraw", file=sys.stderr)
        return 1

    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    data = {}
    for side, colr in (("right", "tab:blue"), ("left", "tab:red")):
        if side not in files:
            continue
        rows = analyse(files[side])
        data[side] = rows
        report(side, rows)
        T, D, F, S, A, DC = (col(rows, k) for k in ("t", "duty", "fpk", "snr", "acrms", "dc"))
        fexp = col(rows, "fexp")
        ax[0, 0].plot(T, np.abs(D) * 10, color=colr, alpha=0.3, label=f"{side}: |duty|×10")
        ax[0, 0].plot(T, F, ".", color=colr, ms=4, label=f"{side}: f_peak")
        ax[0, 0].plot(T, fexp, "--", color=colr, alpha=0.5, lw=0.8)
        ax[0, 1].semilogy(np.abs(D), np.maximum(S, 0.5), ".", color=colr, ms=4, label=side)
        ax[1, 0].plot(np.abs(D), A * 3.3 / 4095 * 1000, ".", color=colr, ms=4, label=side)
        ax[1, 1].plot(np.abs(D), DC * 3.3 / 4095, ".", color=colr, ms=4, label=side)
    ax[0, 0].set_title("Синусная развёртка duty ±100 %, период 8 с: пик спектра vs модель (пунктир)")
    ax[0, 0].set_xlabel("t, с"); ax[0, 0].set_ylabel("Гц"); ax[0, 0].legend(fontsize=8)
    ax[0, 1].axhline(8, color="k", ls=":"); ax[0, 1].set_title("SNR спектрального пика (пик / медиана 60–2500 Гц)")
    ax[0, 1].set_xlabel("|duty|, %"); ax[0, 1].legend()
    ax[1, 0].set_title("Амплитуда пульсаций на входе АЦП"); ax[1, 0].set_xlabel("|duty|, %"); ax[1, 0].set_ylabel("мВ rms"); ax[1, 0].legend()
    ax[1, 1].axhline(3.3, color="k", ls=":"); ax[1, 1].set_title("DC на узле IS (R_IS = 10 кОм, мотор без нагрузки)")
    ax[1, 1].set_xlabel("|duty|, %"); ax[1, 1].set_ylabel("В"); ax[1, 1].legend()
    fig.tight_layout()
    fig.savefig(os.path.join(ART, "is_signal_characterization.png"), dpi=110)

    side = "right" if "right" in files else "left"
    fig2, ax2 = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
    wins = load(files[side])
    for a, (lo, hi) in zip(ax2, [(10, 15), (20, 25), (60, 70)]):
        for _w, (_t, duty, x) in wins.items():
            if lo <= abs(duty) < hi:
                x = np.asarray(x[:400])
                a.plot(np.arange(len(x)) / FS * 1000, x * 3.3 / 4095, lw=0.8)
                a.set_title(f"{side}, duty {duty:+.0f} %: 40 мс сырого IS (10 kSPS, RC 3.2 кГц)")
                a.set_ylabel("В")
                break
    ax2[-1].set_xlabel("мс")
    fig2.tight_layout()
    fig2.savefig(os.path.join(ART, "is_signal_timedomain.png"), dpi=110)
    print("PNG:", os.path.join(ART, "is_signal_characterization.png"), os.path.join(ART, "is_signal_timedomain.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
