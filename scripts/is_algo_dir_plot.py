#!/usr/bin/env python3
"""Visual analysis: per-window pkpk/std/mean_off vs duty for L and R motors."""
import csv, sys
from collections import defaultdict
from pathlib import Path
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
    rows=[]
    for idx,w in sorted(wins.items()):
        s=np.array(w["samples"],dtype=np.float64)
        rows.append((idx,w["duty"],s))
    return rows

def zc_freq(s, sps=10000.0, min_pkpk=120):
    n=len(s); sub=128; cr=0; vs=0
    for i in range(0,n-sub,sub):
        ss=s[i:i+sub]
        if ss.max()-ss.min()<min_pkpk: continue
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

L=load(left_csv); R=load(right_csv)

def metrics(rows, bl):
    d=[];pp=[];std=[];mo=[];zh=[]
    for _,duty,s in rows:
        d.append(duty); pp.append(s.max()-s.min()); std.append(np.std(s))
        mo.append(np.mean(s)-bl); zh.append(zc_freq(s))
    return map(np.array,(d,pp,std,mo,zh))

dL,ppL,stdL,moL,zhL=metrics(L,bl_L)
dR,ppR,stdR,moR,zhR=metrics(R,bl_R)

fig,axes=plt.subplots(4,1,figsize=(13,12),sharex=True)
fig.suptitle("IS-pin metrics vs duty — LEFT (FWD-only) vs RIGHT (bidirectional)")

for ax,(yL,yR,lbl) in zip(axes,[
    (ppL,ppR,"peak-to-peak (ADC counts)"),
    (stdL,stdR,"std-dev (ADC counts)"),
    (moL,moR,"mean − baseline (ADC counts)"),
    (zhL,zhR,"ZC freq (Hz)  [current algo, min_pkpk=120]"),
]):
    ax.scatter(dL,yL,s=14,c='C0',label='LEFT (chip wired only FWD)',alpha=.85)
    ax.scatter(dR,yR,s=14,c='C3',label='RIGHT (both dirs)',alpha=.85,marker='x')
    ax.set_ylabel(lbl); ax.grid(True); ax.legend(loc='upper left',fontsize=8)
    ax.axvline(0,c='k',lw=.5)

# overlay threshold suggestions
axes[1].axhline(50,c='g',ls='--',lw=1,label='std=50 gate')
axes[2].axhline(100,c='g',ls='--',lw=1)
axes[2].axhline(-100,c='g',ls='--',lw=1)
axes[1].legend(loc='upper left',fontsize=8)

axes[-1].set_xlabel("duty %")
plt.tight_layout()
plt.savefig(out_png,dpi=120)
print(f"saved → {out_png}")
