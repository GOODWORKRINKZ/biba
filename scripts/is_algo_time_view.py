#!/usr/bin/env python3
"""Time-domain view: raw ADC stream concatenated across windows + computed metrics."""
import csv, sys
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def load(path):
    wins = defaultdict(lambda: {"samples": []})
    with open(path) as f:
        r = csv.reader(f); next(r)
        for row in r:
            idx=int(row[0]); duty=float(row[2]); val=int(row[4])
            wins[idx]["duty"]=duty
            wins[idx]["samples"].append(val)
    out=[]
    for idx in sorted(wins):
        out.append((idx,wins[idx]["duty"],np.array(wins[idx]["samples"],dtype=np.float64)))
    return out

def zc_freq(s, sps=10000.0, min_pkpk=120, min_std=0.0):
    n=len(s); sub=128; cr=0; vs=0
    for i in range(0,n-sub,sub):
        ss=s[i:i+sub]
        if ss.max()-ss.min()<min_pkpk: continue
        if np.std(ss)<min_std: continue
        vs+=1
        mid=(ss.max()+ss.min())/2
        sign=ss[0]>=mid
        for v in ss[1:]:
            ns=v>=mid
            if ns!=sign: cr+=1; sign=ns
    if vs==0: return 0.0
    return cr/(2*(vs*sub)/sps)

left_csv=sys.argv[1]; right_csv=sys.argv[2]; out_png=sys.argv[3]
bl_L=997.1; bl_R=2027.2
SPS=10000.0
WIN_S=1024/SPS  # 0.1024 s

L=load(left_csv); R=load(right_csv)

# Build a continuous-time stream: each window of 1024 samples at 10kSPS.
# Real gap between windows = ~16 ms (period_ms/n_windows - window_dur).
# We just stack windows back-to-back for visualization purposes.
def stream(rows):
    samp=[]; t=[]; duty_t=[]; duty_v=[]
    for i,(idx,duty,s) in enumerate(rows):
        t0=i*WIN_S  # consecutive window start time
        t.append(t0 + np.arange(len(s))/SPS)
        samp.append(s)
        duty_t.append(t0); duty_v.append(duty)
    return np.concatenate(t), np.concatenate(samp), np.array(duty_t), np.array(duty_v)

tL,sL,dtL,dvL=stream(L)
tR,sR,dtR,dvR=stream(R)

# Per-window metrics
def windowed_metrics(rows, bl):
    t=[];pp=[];std=[];mo=[];zh_cur=[];zh_std=[]
    for i,(idx,duty,s) in enumerate(rows):
        t.append(i*WIN_S + WIN_S/2)
        pp.append(s.max()-s.min())
        std.append(np.std(s))
        mo.append(np.mean(s)-bl)
        zh_cur.append(zc_freq(s,min_pkpk=120,min_std=0))
        zh_std.append(zc_freq(s,min_pkpk=120,min_std=40))
    return map(np.array,(t,pp,std,mo,zh_cur,zh_std))

tmL,ppL,stdL,moL,zhL_cur,zhL_std=windowed_metrics(L,bl_L)
tmR,ppR,stdR,moR,zhR_cur,zhR_std=windowed_metrics(R,bl_R)

fig,axes=plt.subplots(5,1,figsize=(14,14),sharex=True)
fig.suptitle("Time-domain: ±100% sine input vs IS-pin signal & detector outputs")

# Row 0: input duty
ax=axes[0]
ax.plot(dtL,dvL,'b-',label='duty L (= duty R, identical)')
ax.axhline(0,c='k',lw=.4)
ax.set_ylabel("duty %"); ax.grid(True); ax.legend()

# Row 1: raw ADC LEFT
ax=axes[1]
ax.plot(tL,sL,'C0',lw=.5,label='raw ADC LEFT')
ax.axhline(bl_L,c='k',ls=':',lw=.7,label=f'baseline={bl_L:.0f}')
ax.set_ylabel("ADC LEFT"); ax.grid(True); ax.legend(loc='upper right')

# Row 2: raw ADC RIGHT
ax=axes[2]
ax.plot(tR,sR,'C3',lw=.5,label='raw ADC RIGHT')
ax.axhline(bl_R,c='k',ls=':',lw=.7,label=f'baseline={bl_R:.0f}')
ax.set_ylabel("ADC RIGHT"); ax.grid(True); ax.legend(loc='upper right')

# Row 3: std (best discriminator)
ax=axes[3]
ax.plot(tmL,stdL,'C0o-',ms=3,lw=.8,label='std LEFT')
ax.plot(tmR,stdR,'C3x-',ms=4,lw=.8,label='std RIGHT')
ax.axhline(40,c='g',ls='--',lw=1,label='std gate=40')
ax.set_ylabel("std-dev (ADC)"); ax.grid(True); ax.legend()

# Row 4: ZC freq — current algo vs std-gated
ax=axes[4]
ax.plot(tmL,zhL_cur,'C0o:', ms=3,lw=.8,alpha=.7,label='ZC LEFT — current (pkpk-only)')
ax.plot(tmL,zhL_std,'C0s-', ms=4,lw=1.2,label='ZC LEFT — pkpk+std≥40')
ax.plot(tmR,zhR_cur,'C3x:', ms=4,lw=.8,alpha=.7,label='ZC RIGHT — current')
ax.plot(tmR,zhR_std,'C3+-', ms=6,lw=1.2,label='ZC RIGHT — pkpk+std≥40')
ax.set_ylabel("ZC freq (Hz)"); ax.set_xlabel("time (s, windows stacked)")
ax.grid(True); ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(out_png,dpi=120)
print(f"saved → {out_png}")
