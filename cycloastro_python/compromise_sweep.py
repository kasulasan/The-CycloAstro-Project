r"""
compromise_sweep.py
===================
Priority 1 (CLAUDE.md #9): the R_ecc compromise sweep — the direct answer to
Linda's standing objection ("the EKF sits exactly on Zeebe — too good to be
true"). Two demonstrations, both with the real pseudo-measurement filter
(no gating, same loop as compromise_demo.py):

1. SWEEP — seven constant sigma_z values log-spaced 3e-5 .. 3e-2 over 0-10 Myr.
   The old three-value demo (3e-5/9e-5/3e-4) proved K_H is tunable, but every
   curve still LOOKED glued to Zeebe: at 100-yr cadence the steady-state offset
   scales like (REBOUND drift per epoch)/K_H, so even K_H=0.14 erases the slow
   drift. The filter only genuinely releases the reference when sigma_z
   approaches the signal scale (~1e-2). This sweep spans that whole dial and
   measures, in the 5-10 Myr window where the anchors have separated, the RMS
   distance of the estimate to EACH anchor -> a smooth, quantified crossover.

2. AGE-RAMP (Linda's request: reference uncertainty grows with age) — one run
   with sigma_z(t) = 3e-5 * 10^(t / 4 Myr)  (x10 per 4 Myr, ~9.5e-3 at 10 Myr).
   K_H(t) decays from ~0.96 toward ~2.5e-4: the filter tracks Zeebe at young
   ages and releases it gracefully as the assumed reference uncertainty grows.
   HONESTY NOTE: after release the estimate is a free REBOUND-class trajectory.
   It does NOT re-join the pristine REBOUND run pointwise — two nearby chaotic
   trajectories separate on the ~5-Myr Lyapunov time — it stays inside the
   chaotic envelope, decorrelated from both anchors. The ramp rate (x10/4 Myr)
   is an illustrative modeling choice, not a calibrated value.

Pure-REBOUND anchor is reused from results/rebound_300Myr (no recompute);
Zeebe comes from the data module. Runs execute in parallel (one process each).

Usage:
    python compromise_sweep.py            # full run (~6 min wall, 8 workers)
    python compromise_sweep.py --replot   # regenerate figures from saved CSVs
Env: CYCLOASTRO_SWEEP_SPAN_MYR (default 10), CYCLOASTRO_SWEEP_OUT (output dir)

Output: results/compromise_sweep/
    sweep_metrics.csv, sweep_trajectories.csv, age_ramp.csv,
    compromise_sweep.png, age_ramp.png, summary.txt, config.json
"""
import json, os, pathlib, platform, sys, time as _time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cycloastro_core as cc
import cycloastro_zeebe as cz

SPAN_MYR         = float(os.environ.get("CYCLOASTRO_SWEEP_SPAN_MYR", "10"))
SPAN_YR          = int(SPAN_MYR * 1e6)
MEAS_INTERVAL_YR = 100
N_EPOCHS         = SPAN_YR // MEAS_INTERVAL_YR
DT_YR            = cc.DT_YR_DEFAULT
SIGMA_P          = 1e-4          # pseudo-measurement sigma (R_p = SIGMA_P^2)
R_P              = SIGMA_P**2
SIGMA_ACC        = 6e-5
DIM              = cc.DIM48

SWEEP_SIGMAS     = [3e-5, 9e-5, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2]
RAMP             = dict(sigma0=3e-5, decades_per_myr=0.25)   # x10 every 4 Myr
# metrics window (anchors separated) and zoom window; stated for span=10 Myr,
# scaled proportionally for smoke runs at other spans
EVAL_LO_MYR, EVAL_HI_MYR = 0.5*SPAN_MYR, SPAN_MYR
SMOOTH_KYR       = 405                 # running-RMS window (405-kyr ecc cycle)
ZOOM_LO, ZOOM_HI = 0.70*SPAN_MYR, 0.86*SPAN_MYR
N_WORKERS        = 8

OUT = pathlib.Path(os.environ.get("CYCLOASTRO_SWEEP_OUT",
                                  str(pathlib.Path(cc.PROJECT)/"results"/"compromise_sweep")))
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- filter ----
def init_P():
    P = np.zeros((DIM, DIM))
    for i in range(8):
        P[6*i:6*i+3, 6*i:6*i+3]   = np.eye(3)*1e-12
        P[6*i+3:6*i+6, 6*i+3:6*i+6] = np.eye(3)*1e-14
    return P

def build_Q():
    qv = (SIGMA_ACC*DT_YR)**2; qp = qv*DT_YR**2
    SPS = max(1, round(MEAS_INTERVAL_YR/DT_YR))
    d = np.empty(DIM)
    for i in range(8):
        d[6*i:6*i+3] = SPS*qp; d[6*i+3:6*i+6] = SPS*qv
    return np.diag(d)

def pseudo(P_pred, R_p):
    K = P_pred @ np.linalg.inv(P_pred + R_p); IK = np.eye(DIM) - K
    Pa = IK @ P_pred @ IK.T + K @ R_p @ K.T
    return 0.5*(Pa + Pa.T)

def sigma_z_schedule(job):
    """sigma_z at each epoch (t = epoch*MEAS_INTERVAL_YR years before present)."""
    t_myr = np.arange(1, N_EPOCHS+1) * MEAS_INTERVAL_YR / 1e6
    if job["kind"] == "const":
        return np.full(N_EPOCHS, job["sigma_z"])
    return job["sigma0"] * 10.0**(job["decades_per_myr"] * t_myr)

def run_filter(job):
    """Real pseudo-measurement filter (NO gating); identical loop to
    compromise_demo.py except sigma_z may vary per epoch."""
    sig = sigma_z_schedule(job)
    R_p = np.eye(DIM)*R_P; Q = build_Q()
    zb = cz.load_zeebe()
    sim, _ = cc.build_sim(dt_yr=DT_YR, backward=True)
    P = init_P()
    ep = np.empty(N_EPOCHS); kh = np.empty(N_EPOCHS)
    t0 = _time.time()
    for e in range(1, N_EPOCHS+1):
        cc.integrate_to_epoch(sim, e, MEAS_INTERVAL_YR)
        Pa = pseudo(0.5*((P+Q)+(P+Q).T), R_p)
        z = zb.ecc(cc.time_years(sim)); h = cc.eccentricity(sim)
        H = cc.H_earth_48d(sim)
        R_ecc = sig[e-1]**2
        HPH = float((H @ Pa @ H.T)[0, 0]); S = HPH + R_ecc; K = (Pa @ H.T)/S
        cc.set_state48(sim, cc.get_state48(sim) + K.ravel()*(z - h))
        IKH = np.eye(DIM) - K @ H
        Pj = IKH @ Pa @ IKH.T + R_ecc*(K @ K.T)
        P = 0.5*(Pj + Pj.T)
        ep[e-1] = cc.eccentricity(sim); kh[e-1] = HPH/S
    return dict(job=job, e=ep, kh=kh, sig=sig, minutes=(_time.time()-t0)/60)

def _worker(job):           # top-level for pickling
    return run_filter(job)

# ---------------------------------------------------------------- helpers ---
def running_rms(x, win):
    """Centered running RMS over `win` samples."""
    s = pd.Series(np.asarray(x)**2)
    return np.sqrt(s.rolling(win, center=True, min_periods=win//4).mean().values)

def running_mean(x, win):
    return pd.Series(np.asarray(x)).rolling(win, center=True,
                                            min_periods=win//4).mean().values

def rms(x):
    return float(np.sqrt(np.nanmean(np.asarray(x)**2)))

def crossover_sigma(met):
    """sigma_z where rms_to_zeebe == rms_to_rebound (log-interpolated), or None."""
    dlog = np.log10(met.rms_to_zeebe.values) - np.log10(met.rms_to_rebound.values)
    for i in range(len(dlog)-1):
        if dlog[i] < 0 <= dlog[i+1]:
            f_ = dlog[i]/(dlog[i]-dlog[i+1])
            return 10**(np.log10(met.sigma_z[i]) +
                        f_*(np.log10(met.sigma_z[i+1])-np.log10(met.sigma_z[i])))
    return None

# ---------------------------------------------------------------- figures ---
def make_figures(t, e_zb, e_reb, met, sweep_e, ramp_sig, ramp_kh, ramp_e,
                 scale, cross):
    """sweep_e: {sigma_z: eccentricity array}. Saves both PNGs into OUT."""
    smooth = round(SMOOTH_KYR*1000/MEAS_INTERVAL_YR)
    cmap = plt.get_cmap("viridis")
    cols = {s: cmap(i/(len(SWEEP_SIGMAS)-1)) for i, s in enumerate(SWEEP_SIGMAS)}

    # representatives: lambda nearest 0.15 / 0.50 / 0.85, deduplicated
    reps, used = [], set()
    for tgt in (0.15, 0.50, 0.85):
        order = (met.lam - tgt).abs().sort_values().index
        pick = next(i for i in order if i not in used)
        used.add(pick); reps.append(met.sigma_z[pick])

    # ---- figure 1: the dial ----
    fig = plt.figure(figsize=(16, 10), facecolor="white")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1], hspace=0.32, wspace=0.22)
    axA = fig.add_subplot(gs[0, :]); axB = fig.add_subplot(gs[1, 0]); axC = fig.add_subplot(gs[1, 1])
    for a in (axA, axB, axC): a.grid(True, alpha=.25)

    m = (t >= ZOOM_LO) & (t <= ZOOM_HI)
    axA.plot(t[m], e_zb[m], color="#0055AA", lw=2.6, alpha=.55, label="Zeebe ZB20a (reference)")
    axA.plot(t[m], e_reb[m], color="#CC3300", lw=1.6, ls="--", dashes=(6, 3),
             label="pure REBOUND (no filter)")
    for s in reps:
        r = met[met.sigma_z == s].iloc[0]
        axA.plot(t[m], np.clip(sweep_e[s], 0, 0.1)[m], color=cols[s], lw=1.2,
                 label=f"EKF  $\\sigma_z$={s:.0e}   ($K_H$={r.K_H_mean:.2g}, $\\lambda$={r.lam:.2f})")
    axA.set_xlim(ZOOM_LO, ZOOM_HI); axA.set_ylabel("Earth eccentricity")
    axA.set_xlabel("Time before present [Myr]")
    axA.set_title(f"Trajectories, {ZOOM_LO}–{ZOOM_HI} Myr — the estimate genuinely moves "
                  "between the anchors as $\\sigma_z$ grows", fontsize=11)
    axA.legend(loc="upper right", fontsize=8, ncol=2)

    axB.plot(t, running_rms(e_reb - e_zb, smooth), color="k", lw=1.8,
             label="pure REBOUND (outer envelope)")
    for s in SWEEP_SIGMAS:
        axB.plot(t, running_rms(sweep_e[s] - e_zb, smooth),
                 color=cols[s], lw=1.1, label=f"$\\sigma_z$={s:.0e}")
    axB.set_yscale("log"); axB.set_xlim(0, SPAN_YR/1e6)
    axB.set_xlabel("Time before present [Myr]")
    axB.set_ylabel(f"running RMS |EKF − Zeebe|  ({SMOOTH_KYR}-kyr window)")
    axB.set_title("Distance from Zeebe over time: each $\\sigma_z$ picks a level "
                  "between 0 and the REBOUND envelope", fontsize=11)
    axB.legend(loc="lower right", fontsize=7, ncol=2, framealpha=0.9)

    axC.loglog(met.sigma_z, met.rms_to_zeebe, "o-", color="#0055AA", lw=1.8,
               label="RMS distance to Zeebe")
    axC.loglog(met.sigma_z, met.rms_to_rebound, "s-", color="#CC3300", lw=1.8,
               label="RMS distance to REBOUND")
    axC.axhline(scale, color="gray", lw=1, ls=":", label=f"anchor separation ({scale:.1e})")
    if cross:
        axC.axvline(cross, color="k", lw=1, ls="--", alpha=.6)
        axC.annotate(f"balanced\n$\\sigma_z$≈{cross:.1e}", (cross, scale*0.5),
                     fontsize=8, ha="right", va="bottom",
                     xytext=(cross*0.85, 6.5e-5))
    for _, r in met.iterrows():
        axC.annotate(f"$K_H$={r.K_H_mean:.2g}", (r.sigma_z, r.rms_to_zeebe),
                     fontsize=7, xytext=(0, 7), textcoords="offset points", ha="center")
    axC.set_xlabel("measurement noise $\\sigma_z$ (eccentricity)")
    axC.set_ylabel(f"RMS distance, {EVAL_LO_MYR:.0f}–{EVAL_HI_MYR:.0f} Myr window")
    axC.set_title("The dial: $\\sigma_z$ trades distance-to-Zeebe against "
                  "distance-to-REBOUND smoothly", fontsize=11)
    axC.legend(loc="lower right", fontsize=8, framealpha=0.9)

    fig.suptitle("The EKF is a tunable compromise between REBOUND and Zeebe — "
                 "not a transcription of Zeebe", fontsize=14, y=0.985)
    fig.savefig(OUT/"compromise_sweep.png", dpi=150, facecolor="white",
                bbox_inches="tight")
    plt.close(fig)

    # ---- figure 2: age-ramp ----
    dec = slice(None, None, 10)          # decimate to 1-kyr cadence for plotting
    fig, ax = plt.subplots(3, 1, figsize=(15, 11), facecolor="white")
    for a in ax: a.grid(True, alpha=.25)

    ax[0].semilogy(t[dec], ramp_sig[dec], color="#006633", lw=1.8, label="$\\sigma_z(t)$")
    ax[0].set_ylabel("$\\sigma_z(t)$", color="#006633")
    ax0b = ax[0].twinx()
    ax0b.semilogy(t[dec], ramp_kh[dec], color="#990099", lw=0.4, alpha=0.18)
    ax0b.semilogy(t, running_mean(ramp_kh, smooth), color="#990099", lw=1.8,
                  label="$K_H(t)$")
    ax0b.set_ylabel("$K_H(t)$   (running mean; raw trace faint)", color="#990099")
    ax[0].set_title("Reference uncertainty grows with age "
                    f"($\\sigma_z$ ×10 per {1/RAMP['decades_per_myr']:.0f} Myr) "
                    "→ the gain releases the reference", fontsize=11)

    mz = (t >= ZOOM_LO) & (t <= ZOOM_HI)
    ax[1].plot(t[mz], e_zb[mz], color="#0055AA", lw=2.6, alpha=.55, label="Zeebe ZB20a")
    ax[1].plot(t[mz], e_reb[mz], color="#CC3300", lw=1.6, ls="--", dashes=(6, 3),
               label="pure REBOUND")
    ax[1].plot(t[mz], np.clip(ramp_e, 0, 0.1)[mz], color="#006633", lw=1.2,
               label="EKF, age-dependent $\\sigma_z$")
    ax[1].set_xlim(ZOOM_LO, ZOOM_HI); ax[1].set_ylabel("Earth eccentricity")
    ax[1].set_title(f"Trajectory in the diverged window ({ZOOM_LO}–{ZOOM_HI} Myr): "
                    "no longer pinned to Zeebe — a free REBOUND-class trajectory "
                    "inside the chaotic envelope", fontsize=11)
    ax[1].legend(loc="upper right", fontsize=8)

    ax[2].plot(t, running_rms(e_reb - e_zb, smooth), color="k", lw=1.8,
               label="|REBOUND − Zeebe| (anchor separation)")
    ax[2].plot(t, running_rms(ramp_e - e_zb, smooth), color="#0055AA", lw=1.5,
               label="|EKF − Zeebe|")
    ax[2].plot(t, running_rms(ramp_e - e_reb, smooth), color="#CC3300", lw=1.5,
               label="|EKF − REBOUND|")
    ax[2].set_yscale("log"); ax[2].set_xlim(0, SPAN_YR/1e6)
    ax[2].set_xlabel("Time before present [Myr]")
    ax[2].set_ylabel(f"running RMS ({SMOOTH_KYR}-kyr window)")
    ax[2].set_title("Graceful release: young ages track Zeebe; after release the "
                    "estimate stays at the chaotic-envelope level of BOTH anchors "
                    "(re-joining either pointwise is forbidden by chaos)", fontsize=11)
    ax[2].legend(loc="lower right", fontsize=8)

    fig.suptitle("Age-dependent measurement uncertainty: the filter trusts the "
                 "reference only as far as the assumed uncertainty allows",
                 fontsize=14, y=0.99)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(OUT/"age_ramp.png", dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)

# ------------------------------------------------------------------- main ---
def load_anchors():
    t = np.arange(1, N_EPOCHS+1) * MEAS_INTERVAL_YR / 1e6      # Myr before present
    zb = cz.load_zeebe()
    e_zb = np.array([zb.ecc(x*1e6) for x in t])
    reb = pd.read_csv(pathlib.Path(cc.PROJECT)/"results"/"rebound_300Myr"/"rebound.csv")
    e_reb = np.interp(t, np.abs(reb["t_yr"].values)/1e6, reb["e_Earth"].values)
    return t, e_zb, e_reb

def main():
    print("="*70)
    print(f"  COMPROMISE SWEEP — R_ecc dial + age-ramp, 0-{SPAN_YR/1e6:.0f} Myr")
    print("="*70)
    t, e_zb, e_reb = load_anchors()

    jobs = [dict(kind="const", sigma_z=s, name=f"sz{s:.0e}") for s in SWEEP_SIGMAS]
    jobs.append(dict(kind="ramp", name="age_ramp", **RAMP))

    results = {}
    t0 = _time.time()
    with ProcessPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(_worker, j): j["name"] for j in jobs}
        for f in as_completed(futs):
            r = f.result(); results[r["job"]["name"]] = r
            print(f"  done: {r['job']['name']:<10s}  mean K_H={np.nanmean(r['kh']):.4f}"
                  f"  [{r['minutes']:.1f} min]")
    wall_min = (_time.time()-t0)/60
    print(f"  all {len(jobs)} runs finished in {wall_min:.1f} min wall")

    # ---- metrics over the evaluation window (anchors separated) ----
    win = (t >= EVAL_LO_MYR) & (t <= EVAL_HI_MYR)
    scale = rms(e_zb[win] - e_reb[win])           # anchor separation, for scale
    rows = []
    for s in SWEEP_SIGMAS:
        r = results[f"sz{s:.0e}"]
        dz = rms(r["e"][win] - e_zb[win]); dr = rms(r["e"][win] - e_reb[win])
        rows.append(dict(sigma_z=s, K_H_mean=float(np.nanmean(r["kh"])),
                         rms_to_zeebe=dz, rms_to_rebound=dr,
                         lam=dz/(dz+dr)))
    met = pd.DataFrame(rows)
    cross = crossover_sigma(met)
    ramp = results["age_ramp"]

    # ---- CSVs ----
    met.to_csv(OUT/"sweep_metrics.csv", index=False)
    traj = pd.DataFrame({"t_myr": t, "e_zeebe": e_zb, "e_rebound": e_reb})
    for s in SWEEP_SIGMAS:
        traj[f"e_ekf_sz{s:.0e}"] = results[f"sz{s:.0e}"]["e"]
    traj.to_csv(OUT/"sweep_trajectories.csv", index=False, float_format="%.7e")
    pd.DataFrame({"t_myr": t, "sigma_z": ramp["sig"], "K_H": ramp["kh"],
                  "e_ekf": ramp["e"], "e_zeebe": e_zb, "e_rebound": e_reb}
                 ).to_csv(OUT/"age_ramp.csv", index=False, float_format="%.7e")

    make_figures(t, e_zb, e_reb, met,
                 {s: results[f"sz{s:.0e}"]["e"] for s in SWEEP_SIGMAS},
                 ramp["sig"], ramp["kh"], ramp["e"], scale, cross)

    # ---- summary + config ----
    with open(OUT/"summary.txt", "w") as f:
        f.write("COMPROMISE SWEEP — R_ecc dial + age-ramp (priority 1, for Linda)\n")
        f.write(f"span 0-{SPAN_YR/1e6:.0f} Myr, cadence {MEAS_INTERVAL_YR} yr, no gating\n")
        f.write(f"metrics window {EVAL_LO_MYR}-{EVAL_HI_MYR} Myr; "
                f"anchor separation RMS = {scale:.3e}\n\n")
        f.write(met.to_string(index=False, float_format=lambda v: f"{v:.4e}"))
        f.write("\n\nlam = rms_to_zeebe/(rms_to_zeebe+rms_to_rebound): "
                "0 = on Zeebe, 1 = on REBOUND\n")
        if cross:
            f.write(f"balanced trajectory (equal distance to both anchors) at "
                    f"sigma_z ~ {cross:.2e}\n")
        f.write("note: distances of intermediate settings vary at the chaotic-\n"
                "realization level (e.g. 3e-4 vs 1e-3), so the dial is smooth "
                "only to within that variance.\n")
        f.write(f"\nage-ramp: sigma_z(t) = {RAMP['sigma0']:.0e} * 10^(t * "
                f"{RAMP['decades_per_myr']} /Myr)  (x10 per {1/RAMP['decades_per_myr']:.0f} Myr)\n")
        f.write(f"  K_H: {ramp['kh'][0]:.3f} at present -> {ramp['kh'][-1]:.2e} at "
                f"{SPAN_YR/1e6:.0f} Myr\n")
        dz = rms(ramp["e"][win] - e_zb[win]); dr = rms(ramp["e"][win] - e_reb[win])
        f.write(f"  in {EVAL_LO_MYR}-{EVAL_HI_MYR} Myr window: rms to Zeebe {dz:.3e}, "
                f"to REBOUND {dr:.3e} (lam={dz/(dz+dr):.2f})\n")
        f.write("  after release the estimate is a free REBOUND-class trajectory:\n"
                "  it stays inside the chaotic envelope but does NOT re-join either\n"
                "  anchor pointwise (Lyapunov ~5 Myr). Ramp rate is illustrative.\n")
        f.write(f"\nwall time {wall_min:.1f} min ({N_WORKERS} parallel workers)\n")

    import rebound
    with open(OUT/"config.json", "w") as f:
        json.dump(dict(
            script="compromise_sweep.py",
            timestamp=datetime.now(timezone.utc).isoformat(),
            span_yr=SPAN_YR, meas_interval_yr=MEAS_INTERVAL_YR, dt_yr=DT_YR,
            sigma_p=SIGMA_P, sigma_acc=SIGMA_ACC, gating="none",
            sweep_sigmas=SWEEP_SIGMAS, ramp=RAMP,
            eval_window_myr=[EVAL_LO_MYR, EVAL_HI_MYR], smooth_kyr=SMOOTH_KYR,
            rebound_anchor="results/rebound_300Myr/rebound.csv",
            n_workers=N_WORKERS, wall_minutes=round(wall_min, 1),
            runtimes_min={k: round(v["minutes"], 1) for k, v in results.items()},
            versions=dict(python=sys.version.split()[0], numpy=np.__version__,
                          pandas=pd.__version__, rebound=rebound.__version__),
            host=platform.node()), f, indent=2)

    print(f"\n  saved -> {OUT}")
    print(met.to_string(index=False, float_format=lambda v: f"{v:.4e}"))
    if cross:
        print(f"  balanced trajectory at sigma_z ~ {cross:.2e}")

def replot():
    """Regenerate both figures from the saved CSVs (no filter re-runs)."""
    print("  replot: regenerating figures from saved CSVs")
    met = pd.read_csv(OUT/"sweep_metrics.csv")
    traj = pd.read_csv(OUT/"sweep_trajectories.csv")
    ar = pd.read_csv(OUT/"age_ramp.csv")
    t = traj["t_myr"].values
    e_zb = traj["e_zeebe"].values; e_reb = traj["e_rebound"].values
    sweep_e = {s: traj[f"e_ekf_sz{s:.0e}"].values for s in SWEEP_SIGMAS}
    win = (t >= EVAL_LO_MYR) & (t <= EVAL_HI_MYR)
    scale = rms(e_zb[win] - e_reb[win])
    make_figures(t, e_zb, e_reb, met, sweep_e,
                 ar["sigma_z"].values, ar["K_H"].values, ar["e_ekf"].values,
                 scale, crossover_sigma(met))
    print(f"  saved -> {OUT/'compromise_sweep.png'}\n  saved -> {OUT/'age_ramp.png'}")

if __name__ == "__main__":
    replot() if "--replot" in sys.argv else main()
