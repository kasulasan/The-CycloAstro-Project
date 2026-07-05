# CycloAstro — What works / What doesn't (6 months distilled)

**The debugging ledger, Jan–Jul 2026. Read before trying anything "new" — most
ideas have already been tried. Detail lives in `CYCLOASTRO_PROJECT_HISTORY.md`
(meeting-by-meeting), `AUDIT_2026-07-02.md`, and `CLAUDE.md`.**

---

## ✅ VALIDATED — works, keep, build on

| What | Evidence |
|---|---|
| **Pseudo-measurement** (H=I₄₈, z=x_pred, R_p=1e-8) to bound the 47 unobserved directions | P flat at 6.6e-9 across 300 Myr, no clamp; the fix that ended the P-explosion era (Jun 1→15) |
| **ZB as measurement, tiny R, NO added noise; F & H from REBOUND** | Jonathan's Apr 13 prescription; the only formulation that ever tracked honestly |
| **Earth-only analytic H (LRL derivative)** | FD-verified to 1.1e-4; gate TEST 2/3 |
| **Two separate simulations** (sim_true / sim_est) | Single-sim leakage corrupted weeks of comparisons (found May 18) |
| **Exact-time integration** (`sim.integrate(target)`) | Fixed-substep loops drift ~100 yr / 20k epochs |
| **WHFast cache flag after every state write** | Without it corrections are silently discarded (safe_mode=0) |
| **Joseph-form updates + symmetrization** | P stays SPD; gate TEST 8/9 |
| **Per-planet 6×6 measurement updates** | 300 Myr in ~2.75 h instead of days (Jun 15) |
| **Full-state checkpoint incl. the SUN + P + t** | Resume bit-identical (0.0 diff); planets-only restore = 16 AU error (gate TEST 11) |
| **NIS gate (25) within the reliable range** | 58% gating in deep-chaos zones, coasts on REBOUND correctly |
| **Hand-off to pure REBOUND past ~8 Myr** | Only honest deep-time trajectory (`best_estimate_300Myr.py`) |
| **Compromise via σ_z sweep** | Full dial `compromise_sweep.py` (2026-07-05, supersedes `compromise_demo.py`): λ (trajectory position ZB→REB) 0.00→0.91 over σ_z 3e-5→3e-2; balanced at σ_z≈7.5e-3; age-ramp σ_z(t)=3e-5·10^(t/4 Myr) gives graceful release — the answer to Linda's concern. CAUTION: K_H is per-update gain, NOT trajectory position — K_H=0.14 still sits on Zeebe; midway needs K_H≪0.5. After release the estimate is a free REBOUND-class trajectory (no pointwise re-join — Lyapunov) |
| **Leave-one-out influence demo** | No-Jupiter halves Earth's e-range; 405-kyr line = Venus–Jupiter beat |
| **The 30-check gate as workflow** | Caught a bug in its own fix (Sun-in-snapshot) the day it was written |
| **60-Myr headline result** | mean \|ZB−EKF\| = 1.2e-5, K_H 0.907±0.040 — the defensible number |

## ❌ TRIED AND FAILED — do not retry

| What | Why it fails | When learned |
|---|---|---|
| **Φ = I + F·dt** | First-order Euler; unstable — and *worse* once F is corrected (eig solver failure) | Apr–Jul |
| **Hand-built dynamics Jacobians in general** | Bug factory: missing Sun (TWICE — Mar 23 and Jun 29), dE/dV factor-2, velocity sign regression | recurring |
| **Textbook Cartesian Φ-propagated covariance** ("correct H" coupling) | Diverges in ~1.5 kyr; Mercury gain → 1e6; orbital-phase drift is fundamental, not tuning | Jul 2 |
| **P-ceiling reset** | Band-aid; fired 838× even in the "best" run — masked the disease | Apr 27–May 11 |
| **Alpha / bisection gain-scaling** | Band-aid; inconsistent unless fed back into P; Jonathan: "not kosher" | Apr 27 |
| **Any Q tuning to fix divergence** | "No amount of Q adjustment fixes it — the problem is not in Q" | May 4–11 |
| **Per-planet Q values** | No improvement over Earth-only Q (both 68%) | May 4–11 |
| **Tiny Q everywhere** | Filter can't move the planets at all (Jonathan's engineering concern) | May 4 |
| **One shared simulation for model + reference** | Filter leaks into its own truth; explains every "REBOUND changed" mystery | May 18 |
| **48-only (planets-only) state snapshot** | The Sun orbits the barycenter — restore is dynamically inconsistent (16 AU) | Jul 2 |
| **Naive EnKF, N=16, no localization** | Sampling noise dominates: Neptune gain > Jupiter (backwards physics), diverges | Jun–Jul |
| **Non-zero H entries for other planets** ("fixing" H) | Conceptually wrong: H = what the scalar is computed from; H≈0 ⇒ filter ignores the measurement. Influence lives in F/Φ | Jun 29–Jul 2 |
| **Bare transition-matrix prediction (no REBOUND)** | "That's not a correct formulation for the filter" — F has to be rebound | Apr 13 |
| **1-yr measurement interval** | NIS 0.006, absurd overconfidence, no benefit | Mar 16 |
| **Decimation (old code)** | Obsolete; removed | Mar 16 |
| **Hopper cluster** | 12-h job cap vs multi-day runs | Mar 16 |
| **Sine-wave toy retreat** | Rejected: "the physics are important; this is as good a test case as we can get" | May 11 |
| **Trusting the EKF past ~90 Myr** | Once REBOUND itself decorrelates, NIS gate self-defeats (inflated S hides bad updates) | Jul 2 |
| **"Tracks cleanly to 132 Myr" claim** | False — mis-computed summary. Clean range ≈ 8 Myr | on record |
| **Post-vs-pre "improvement factors"** | Leakage-prone; only the comparison vs an *independent* REBOUND run is defensible | on record |

## ⚠️ FLAGGED — known limits, on record, not bugs

- Mercury under-resolved at dt=0.035 (needs ≤0.012 if its own track matters).
- Zeebe `Inc` column is **degrees**; core `inclination()` returns **radians** — unit trap if inclination is ever fused.
- `initialParticles.py` exists in 3 byte-identical copies (canonical: `KalmanFilterFunctions/`).
- `cycloastro_pseudo_ekf.py` is deliberately self-contained — keep in sync with core by hand.
- ICs are Horizons epoch 2000-12-31, not exactly J2000 (irrelevant at Myr scale; say it correctly).
- J2_SUN = 2.2e-7 kept (within Pijpers' 2.18±0.06e-7) for run-to-run reproducibility.
- Pseudo-measurement itself is, in Jonathan's words, "sort of a cheat… not completely kosher" — honest framing required, it *bounds*, it does not couple.
