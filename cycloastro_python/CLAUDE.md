# CLAUDE.md — CycloAstro project context

This file is auto-loaded by Claude Code. It is the handoff/"memory" of the
project so a fresh session can continue with full context. Read it top to
bottom before doing anything.

---

## 1. What this project is

**Goal:** reconstruct Earth's orbital eccentricity backward in time by fusing a
high-fidelity N-body integration (REBOUND) with a published paleo-astronomical
reference (Zeebe ZB20a), using an Extended Kalman Filter (EKF) that produces a
*quantified-uncertainty* trajectory — not just a number.

**Why:** Earth's eccentricity drives the Milankovitch climate cycles. Past the
inner-Solar-System Lyapunov time (~5 Myr) a single integration drifts
unpredictably and carries no uncertainty. The EKF anchors REBOUND to the
reference where the reference is reliable and degrades gracefully after.

**People:**
- **Santosh** — the user / does the work.
- **Jonathan** — supervisor. Reviews documents carefully; cares about
  mathematical correctness and that references are real.
- **Linda** — colleague providing an external proxy dataset (53–58 Mya) to be
  scaled to eccentricity and used in place of Zeebe in that window (pending).

---

## 2. Environment & how to run

- **Python:** conda env `cycloastro`. From the shell use the explicit interpreter:
  `/opt/anaconda3/envs/cycloastro/bin/python`. It has rebound (4.4.10), reboundx,
  numpy, scipy, pandas, matplotlib, pypandoc.
- Santosh normally runs scripts in **Jupyter** via `%run "<abs path>"`.
- The `pkg_resources is deprecated` and `velocity-dependent force to WHFAST`
  warnings are **benign** — filter them out of any captured output.
- **Always run the test suite first** as a gate:
  `%run cycloastro_tests.py` → must print `ALL CHECKS PASSED` (30 checks).
- Long runs: wrap with `caffeinate` tied to the process, e.g. in a Jupyter cell
  `subprocess.Popen(["caffeinate","-i","-d","-w",str(os.getpid())])`.
- **Files live in this directory** (`cycloastro_python/`), not in the
  `.claude/worktrees/...` path. Use absolute paths to this directory.

---

## 3. Architecture — single source of truth (IMPORTANT)

Every historical bug in this project came from **duplicated, inconsistent code
across scripts** (a sign-error in a Jacobian, the WHFast cache, a timestep
drift, scripts silently diverging). The fix was to consolidate onto ONE core
and gate it with automated tests. **Do not re-introduce duplicated physics.**

| File | Role | Imports |
|---|---|---|
| `cycloastro_core.py` | **Single source of truth**: constants, `build_sim`, state I/O (with the WHFast cache fix), eccentricity, inclination, H Jacobians (6D+48D), energy, exact-time integration | REBOUND only |
| `cycloastro_zeebe.py` | Zeebe ZB20a reference data: load + cubic spline + validity range. **No physics, no filter.** | data only |
| `cycloastro_tests.py` | 30 automated checks (Jacobian vs finite-diff, energy conservation, exact-time landing, determinism, pseudo-measurement algebra, 2-body sanity, faithful checkpoint-restore). **The gate.** | the core |
| `pipeline_rebound.py` | Pure REBOUND run, all 8 planets. Span via env var. | core |
| `pipeline_kalman.py` | The production pseudo-measurement EKF. Span via env var. | core + zeebe |

The three concerns (reference / dynamics / fusion) stay in separate modules;
they meet only inside the filter, which is what a filter is.

**Span is a parameter, not a copy:** set `CYCLOASTRO_SPAN_MYR` (default 60;
floats accepted, e.g. `"0.002"` = 2 kyr for smoke tests).
```python
import os; os.environ["CYCLOASTRO_SPAN_MYR"]="300"; %run pipeline_kalman.py
```
`run_300Myr.py` launches the full 300-Myr Kalman+REBOUND with caffeinate.

**Faithful checkpoint/resume (added 2026-07-02):** `pipeline_kalman.py` and
`cycloastro_pseudo_ekf.py` snapshot the **full 54-state (Sun + 8 planets) +
sim.t + P** to `filter_state.npz` at every checkpoint, and resume from it
bit-identically (verified end-to-end: interrupted+resumed == uninterrupted,
0.0 diff on every column). Two lessons encoded in gate TEST 11:
(1) resuming from the CSV alone silently discards all Kalman corrections
(~1e-1 state error after 10 epochs) and resets P (~6e3× too small);
(2) a planets-only (48) snapshot is NOT faithful — the Sun orbits the
barycentre, so it must be saved too (48-only restore → ~16 AU error in 1 kyr).
`cycloastro_pseudo_ekf.py` accepts env overrides `PSEUDO_RUN_NAME`,
`PSEUDO_SPAN_YR`, `PSEUDO_CHECKPOINT_EVERY`, `PSEUDO_PROGRESS_EVERY`;
`pipeline_kalman.py` accepts `CYCLOASTRO_CHECKPOINT_EVERY`.

**Known duplication (watch, don't worsen):** `initialParticles.py` exists in
3 byte-identical copies (root, `KalmanFilterFunctions/` = canonical, `debug/`);
`cycloastro_pseudo_ekf.py` is deliberately self-contained (own build_sim etc.)
per the supervisor-prescription rework — keep it consistent with the core.
ICs are JPL Horizons, epoch **2000-12-31 00:00** (not exactly J2000; irrelevant
at Myr scale but say it correctly).

---

## 4. The physics & math you must keep straight

### The pseudo-measurement (the core method; supervisor's prescription)
A scalar eccentricity measurement constrains only 1 of the 48 state directions;
the other 47 diverge in a plain EKF. The **pseudo-measurement** treats REBOUND's
own propagated full state as a measurement with `H = I₄₈`, value `z = x_pred`
(so innovation = 0; the estimate doesn't move), noise `R_p`. The covariance
update is the parallel combination `P⁺ = (P⁻¹ + R_p⁻¹)⁻¹`, which **caps** the
unobserved directions at `R_p` (physical: "REBOUND is trusted to this level")
and **preserves** the eccentricity direction for Zeebe. This replaced three
removed patches: P_CEILING, Lyapunov-scaled Q, and bisection. See
`PSEUDO_MEASUREMENT_EXPLAINED.md`.

### H vs F — where the planets enter (Jonathan asked about this; settle it correctly)
- **H = ∂(Earth eccentricity)/∂(state)** is the *instantaneous measurement*
  Jacobian. Earth's eccentricity is a geometric property of Earth's own orbit
  (Laplace–Runge–Lenz), so **H is non-zero ONLY in Earth's columns** (1.03 for
  Earth, exactly 0 for every other planet). This is correct, verified by finite
  difference (`check_H_and_K.py`).
- The other planets DO drive Earth's eccentricity — but **over time, through the
  dynamics F** (`∂a_Earth/∂(planet)`), which is non-zero for all planets
  (Jupiter & Venus dominant). The coupling lives in **F, not H**.
- If the goal becomes "let the eccentricity measurement correct the OTHER
  planets," that requires cross-correlations in P (Φ-propagation or an ensemble),
  NOT a non-zero H.
- **The settled language now lives in the code** (2026-07-02): the precise
  H-vs-F semantics are written into `cycloastro_core.py` Section 6 and
  `cycloastro_pseudo_ekf.compute_H48`'s docstring — H = which variables the
  measured scalar is computed from (a property of the measurement map, NOT
  "influence"); dynamical influence = F; finite-time sensitivity = H·Φ
  (non-zero for all planets). Do not describe H in terms of "influence".
- Empirical caution (2026-06-29): the textbook Cartesian Φ-propagated EKF was
  built and tested — the gain does reach all planets, but it diverges after
  ~1.5 kyr (Mercury gain → ~10⁶): Cartesian covariance propagation is unstable
  (orbital-phase drift). Genuine cross-planet correction needs an ensemble or
  orbital-element coordinates. This is WHY the pseudo-measurement bounds
  rather than couples.

### K is a vector; K_H is a scalar diagnostic
The Kalman gain `K = P Hᵀ/S` is a **48×1 vector**. The number "0.93" in earlier
docs is `K_H ≡ H·K = HPHᵀ/S`, the *fraction of the innovation applied along the
eccentricity direction* — a consistency diagnostic, not the gain. (Jonathan
flagged this; the report is now corrected.)

### Other essentials
- WHFast `safe_mode=0` caches Jacobi coords — after ANY `set_state*`, you MUST
  set `sim.ri_whfast.recalculate_coordinates_this_timestep = 1` or the
  correction is silently discarded. (Lives inside core's `set_state`/`set_state48`.)
- Use **exact-time integration** (`integrate_to_epoch`, `sim.integrate(target)`),
  never a loop of `SPS` fixed substeps — the latter drifts ~100 yr over 20k epochs.
- Use **Joseph-form** covariance updates + explicit symmetrization.
- `dt = 0.035 yr` (~28 substeps/Earth orbit). NOTE: Mercury (88 d) is
  under-resolved at this dt and its eccentricity numerically collapses near
  −1 Myr; its direct effect on Earth is tiny so we kept dt=0.035 (decision on
  record). Resolve with dt ≤ 0.012 if Mercury's own track matters.

---

## 5. Key results (numbers to trust)

- **Covariance bounded** at P_max ≈ 6.6×10⁻⁹ flat across the run, capped by the
  physical R_p = 1×10⁻⁸. No clamp. (Validation: a 1e6 prior → exactly R_p.)
- **K_H ≈ 0.93 ± 0.03** (genuine fusion, not transcription).
- **Decorrelation / hand-off at ~7.9 Myr**: REBOUND and Zeebe chaotically
  separate there; the EKF tracks cleanly before, and past it a single scalar
  channel cannot pin the orbit (corrections actively corrupt it past ~60–90 Myr
  in the ungated run). The honest reconstruction hands off to pure REBOUND after
  ~8 Myr (`best_estimate_300Myr.py`) and stays physical (e ≤ 0.066) to 300 Myr.
- **Pure REBOUND diverges from Zeebe** at 5×10⁻³ @5.1 Myr, 1×10⁻² @7.2 Myr,
  2×10⁻² @12 Myr (matches what Jonathan recalled). `ekf_vs_rebound_divergence.py`.
- **Compromise via covariance tuning** (2026-07-05, `compromise_sweep.py`,
  supersedes `compromise_demo.py`): K_H is the *per-update* gain, NOT the
  trajectory's position — at 100-yr cadence corrections accumulate, so even
  K_H=0.14 stays glued to Zeebe (steady offset ~ drift/K_H). Measured in
  trajectory space over 5–10 Myr (λ = d_ZB/(d_ZB+d_REB); anchor separation
  5.2e-3 RMS): σ_z 3e-5→λ≈0.00 (production), 3e-4→0.13, 1e-2→0.58,
  3e-2→0.91; **balanced trajectory at σ_z ≈ 7.5e-3** (K_H there ~3e-4).
  Age-ramp run (Linda's ask): σ_z(t)=3e-5·10^(t/4 Myr) → K_H 0.96→2.5e-4,
  graceful release ~2.5–5 Myr; after release the estimate is a *free
  REBOUND-class trajectory* (does NOT re-join either anchor pointwise —
  Lyapunov). Figures + CSVs in `results/compromise_sweep/`; note for Linda:
  `NOTE_for_Linda_compromise_sweep.md`/`.docx`.

### Honesty notes (do not over-claim)
- The "within-filter improvement factor" (e.g. 13.6×) is post-vs-pre, NOT a
  leakage-free number; the clean comparison vs an independent pure-REBOUND run
  is the defensible one (~30–130× depending on span).
- A previous claim that "the EKF tracks cleanly to ~132 Myr" was **wrong** (came
  from a mis-computed summary). Real clean range is ~8 Myr; document it honestly.
- `pipeline_kalman.py` contains **NIS validation gating** (`NIS_GATE=25`,
  Bar-Shalom robust KF). It is legitimate and stays, but it was added after the
  first report draft — keep code and docs in sync.
- **(2026-07-02) 300-Myr rerun finding:** the gated EKF goes unphysical past
  ~90 Myr — once REBOUND itself has decorrelated from Zeebe, the NIS gate
  self-defeats (a huge unphysical state inflates HPHᵀ, so S grows and NIS looks
  "consistent", letting bad corrections through). Not a new bug; it is the known
  chaos limit made visible. Defensible headline = the **60-Myr run**
  (mean |ZB−EKF| = 1.2×10⁻⁵, K_H = 0.907±0.040, P flat at 6.6×10⁻⁹). Deep time
  requires the hand-off. Prior 300-Myr results preserved in
  `results/kalman_300Myr_pre20260702/`.

---

## 6. Supervisor (Jonathan) — status of his requests

1. **Compromise via covariance** — DONE (`compromise_demo.py`, figure in
   `results/compromise/`).
2. **Use Linda's data (53–58 Mya) scaled to eccentricity** — framework DONE
   (`external_measurement.py`, validated to noise floor). **Awaiting Linda's CSV**
   (need: time + units, proxy values, optional σ, and which calibration —
   default `match-moments`, which needs only overlap with Zeebe).
3. **Pseudo-measurement explanation** — DONE (`PSEUDO_MEASUREMENT_EXPLAINED.md`).
   (He referenced an "attached document" we never received — ask to align notation.)
4. **H matrix / K vector concerns** — RESOLVED: K wording fixed; H is correctly
   Earth-only (measurement Jacobian) with coupling in F — evidence in
   `check_H_and_K.py`, explained in report §3.2.1. **Open:** confirm with him
   whether he intends a non-standard measurement model (eccentricity sensing the
   perturbers) — if so that's a real design change (cross-correlations in P).
5. **Plot to ≥10 Myr showing where REBOUND diverges** — DONE
   (`results/divergence/ekf_vs_rebound_divergence.png`).
6. **(Jun 29) "Run the long ZB assimilation with the CORRECT (all-planet) H"** —
   answered empirically 2026-07-02: the textbook Cartesian Φ-propagated EKF was
   built (`ekf_rebound_v2.py`); its gain DOES reach all planets but it diverges
   after ~1.5 kyr (Mercury gain → ~10⁶) — Cartesian covariance propagation is
   fundamentally unstable. That is WHY the production filter bounds (pseudo-
   measurement) instead of couples. Stable coupling routes if he insists:
   ensemble KF (`enkf_core.py`, needs localization) or orbital-element space.
   Present it as "your question, answered with a demonstration", not a refusal.
7. **Runnable package / plain-math manual** — asked ≥4 times (Mar 16, Apr 27,
   May 11, Jun 15). Partly served by the codebook docs; a one-command runnable
   bundle for HIS machine is still owed.

---

## 7. Output layout

Each run writes to `results/<name>/`:
`*.csv` (per-epoch data), `summary.txt`, `config.json` (params + versions +
timestamp), `*.png` figures. Existing: `pseudo_2myr/`, `kalman_60Myr/`,
`kalman_300Myr/` (note `kalman_ungated.csv` preserved there), `rebound_60Myr/`,
`rebound_300Myr/`, `divergence/`, `best_estimate/`, `deep_time/`, `compromise/`,
`compromise_sweep/` (the R_ecc dial + age-ramp; `--replot` regenerates figures
from the saved CSVs without re-running the filters).

Documents: `CYCLOASTRO_REPORT.md`/`.docx` (full technical report, references
verified), `PSEUDO_MEASUREMENT_EXPLAINED.md`. Convert MD→DOCX with pypandoc:
`pypandoc.convert_file(src,"docx",outputfile=dst,extra_args=["--toc","--resource-path","."])`.

**Document inventory (2026-06-29 → 07-02, all in this dir, md + docx):**
- `WHAT_WORKS_WHAT_DOESNT.md` — **the 6-month debugging ledger: every validated
  technique, every dead end (do-not-retry list), every flagged limit. Check it
  BEFORE proposing any approach — most ideas were already tried.**
- `CYCLOASTRO_PROJECT_HISTORY` — **full synthesis of all 13 Zoom meetings
  (Mar 16–Jun 29) + decisions + Jonathan/Linda profiles + timeline. READ THIS
  for any people/history question instead of asking.**
- `AUDIT_2026-07-02` — production-readiness audit (bugs found/fixed, verdicts).
- `CYCLOASTRO_CODEBOOK_2026-07-02` — consolidated line-by-line code walkthrough
  (supersedes `CODE_LINE_BY_LINE`, `CODE_COMPLETE_REFERENCE`, `CODE_PLUMBING`).
- `CYCLOASTRO_technical_summary` — H/F/filter explainer for Jonathan.
- `NOTE_for_Jonathan_consolidated` (+ `_H_vs_F`, `_H_earth_vs_others`,
  `PROGRESS_Jonathan_feedback_status`) — meeting notes/scorecards already shared.
- Key figures: `results/planet_influence/influence.png` (leave-one-out:
  no-Jupiter halves Earth's e-range, 405-kyr line collapses ~10×),
  `results/kalman_60Myr/zeebe_ekf_long.png` (EKF vs ZB vs REBOUND, 6 Myr/600 kyr).

---

## 8. Verified references (do NOT fabricate citations)

- Kalman 1960, *J. Basic Eng.* 82(1), 35–45.
- Laskar 1989, *Nature* 338, 237–238 (inner-SS chaos, Lyapunov ≈ 5 Myr).
- Pijpers 1998, *MNRAS* 297(3), L76–L80 (J₂☉ = 2.18×10⁻⁷).
- Quinn, Tremaine & Duncan 1991, *AJ* 101, 2287–2305 (Earth–Moon as quadrupole + GR).
- Rein & Liu 2012, *A&A* 537, A128 (REBOUND).
- Rein & Tamayo 2015, *MNRAS* 452(1), 376–388 (WHFast).
- Tamayo, Rein, Shi & Hernandez 2020, *MNRAS* 491(2), 2885–2901 (REBOUNDx).
- Wisdom & Holman 1991, *AJ* 102, 1528–1538; Wisdom 2006, *AJ* 131(4), 2294–2298.
- Bucy & Joseph 1968 (Joseph form); Simon 2006, *Optimal State Estimation*, ch.7.
- **Zeebe & Lourens 2022, *EPSL* 592, 117595 — defines ZB20a (300–0 Ma).**
  (Common error to avoid: it is NOT "2020, EPSL 530, 115946".)

---

## 9. Likely next tasks

**Hard deadline: Linda's workshop, Aug 17–19, 2026, Baltimore ("The Study"
hotel; virtual option). Something presentable must exist by then.**

Priority order (updated 2026-07-05):
1. ~~**R_ecc "compromise" sweep**~~ — **DONE 2026-07-05** (`compromise_sweep.py`,
   `results/compromise_sweep/`, `NOTE_for_Linda_compromise_sweep.md`/`.docx`).
   Key finding recorded in §5. Workshop figures: `compromise_sweep.png`
   (the dial) + `age_ramp.png` (age-growing σ). Not yet shown to Linda.
2. **Runnable bundle + plain-math manual for Jonathan** — owed since March.
3. **Real data onboarding** — Linda's Tanner A/B (protocol agreed Apr 6: average
   the two, normalize to Laskar min/max; `external_measurement.py` is ready) and
   Richard Hester's DE-ephemeris anchor (geological records give variations only).
4. Bake the decorrelation hand-off natively into `pipeline_kalman.py` (pristine
   parallel REBOUND, switch past ~8 Myr) so one run yields the physical 300-Myr
   trajectory.
5. If Jonathan still wants genuine cross-planet correction after seeing the
   divergence demo: ensemble KF with localization (`enkf_core.py` — its naive
   N=16 run diverged, Neptune-gain > Jupiter = sampling noise) or
   orbital-element-space reformulation (the deeper fix).

---

## 10. Working style that fits this user

- They run things in Jupyter and paste output back; give exact `%run` commands
  with absolute paths.
- Be honest about uncertainty and correct your own errors promptly (there's a
  track record of catching real bugs — do not paper over issues).
- Keep figures clear and labeled; they care about presentation for the supervisor.
- Don't fabricate anything (citations, numbers). Verify, then state.
