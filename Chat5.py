# Full runnable EKF with local instantaneous F from REBOUND variations
import numpy as np
import rebound
import matplotlib.pyplot as plt

# -------------------------
# Helpers: state get/set, eccentricity analytic derivative
# -------------------------
def get_state(sim, planet_indices):
    """Return state vector for given planet_indices (skip Sun if not in list)."""
    state = []
    for idx in planet_indices:
        p = sim.particles[idx]
        state.extend([p.x, p.y, p.z, p.vx, p.vy, p.vz])
    return np.array(state)

def set_state(sim, planet_indices, state):
    """Set state vector back into sim for given planet_indices."""
    idx = 0
    for pi in planet_indices:
        p = sim.particles[pi]
        p.x, p.y, p.z, p.vx, p.vy, p.vz = state[idx:idx+6]
        idx += 6

def get_earth_ecc(sim, earth_index):
    """Return scalar eccentricity of Earth (particle earth_index)."""
    orbit = sim.particles[earth_index].calculate_orbit(primary=sim.particles[0])
    return orbit.e

def de_dx_row(sim, earth_index, planet_indices):
    """
    Analytic measurement Jacobian: 1 x (6 * n_planets) row of de/dX,
    where X orders planets in planet_indices.
    Uses analytic linearization of evec.
    """
    mu = sim.G * (sim.particles[0].m + sim.particles[earth_index].m)
    rE = np.array([sim.particles[earth_index].x,
                   sim.particles[earth_index].y,
                   sim.particles[earth_index].z])
    vE = np.array([sim.particles[earth_index].vx,
                   sim.particles[earth_index].vy,
                   sim.particles[earth_index].vz])
    rnorm = np.linalg.norm(rE)
    h = np.cross(rE, vE)
    evec = np.cross(vE, h)/mu - rE / rnorm
    e_norm = np.linalg.norm(evec)
    if e_norm == 0:
        ehat = np.zeros(3)
    else:
        ehat = evec / e_norm

    row = []
    # for each planet in the filter state, compute 6 partials
    for pi in planet_indices:
        # we only need the current rE, vE and the variation basis dr/dv of planet pi
        for comp_idx in range(6):
            dr = np.zeros(3)
            dv = np.zeros(3)
            if comp_idx < 3:
                dr[comp_idx] = 1.0
            else:
                dv[comp_idx - 3] = 1.0

            # devec linearized (position + velocity contributions)
            # careful: formula derived earlier
            # velocity contributions:
            term_v = (np.cross(dv, h) + np.cross(vE, np.cross(dr, vE))) / mu
            # position contributions:
            term_r = - dr / rnorm + (np.dot(rE, dr) / (rnorm**3)) * rE
            devec = term_v + term_r

            # scalar derivative = ehat · devec
            row.append(float(np.dot(ehat, devec)))
    return np.array(row).reshape(1, -1)  # shape (1, 6*n_planets)

# -------------------------
# Compute local state transition F_k using a clone of sim_est + variations
# -------------------------
def compute_local_F(sim_est, planet_indices, dt):
    """
    Compute local instantaneous state transition matrix F = ∂x(t+dt)/∂x(t)
    for the current sim_est state using REBOUND variations.
    - sim_est: the filter simulation at time t (will NOT be modified)
    - planet_indices: list of particle indices included in the filter state
    - dt: integration step to compute local transition
    Returns F of shape (6*n, 6*n)
    """
    n = len(planet_indices)
    state_dim = 6 * n

    # Clone the sim_est (so we can add variations without affecting sim_est)
    sim_var = sim_est.copy()

    # Add one variation per state component (total state_dim variations)
    variations = []
    for pi_idx, pi in enumerate(planet_indices):
        for comp_idx in range(6):
            v = sim_var.add_variation()
            # initialize variation: set that particle's chosen component = 1
            if comp_idx == 0:
                v.particles[pi].x = 1.0
            elif comp_idx == 1:
                v.particles[pi].y = 1.0
            elif comp_idx == 2:
                v.particles[pi].z = 1.0
            elif comp_idx == 3:
                v.particles[pi].vx = 1.0
            elif comp_idx == 4:
                v.particles[pi].vy = 1.0
            elif comp_idx == 5:
                v.particles[pi].vz = 1.0
            variations.append(v)

    # Integrate the clone forward by dt
    t0 = sim_var.t
    sim_var.integrate(t0 + dt)

    # Build F: each variation j gives a column (response of all planets' states)
    F = np.zeros((state_dim, state_dim))
    for j, v in enumerate(variations):
        col = []
        for pi in planet_indices:
            # v.particles[pi] stores linearized response of particle pi to variation j
            dp = v.particles[pi]
            col.extend([dp.x, dp.y, dp.z, dp.vx, dp.vy, dp.vz])
        F[:, j] = np.array(col, dtype=float)
    return F


def planet_process_noise(dt, sigma_a, n_planets):
    """
    Build block-diagonal Q matrix for n_planets (each 6 states: [x,y,z,vx,vy,vz]).

    Parameters
    ----------
    dt : float
        Time step (same units as state propagation, e.g. REBOUND's time).
    sigma_a : float
        Standard deviation of acceleration noise (AU/yr^2 if using REBOUND units).
    n_planets : int
        Number of planets (default 8 for solar system planets).

    Returns
    -------
    Q : np.ndarray
        (6*n_planets, 6*n_planets) process noise covariance.
    """
    # 3x3 identity
    I3 = np.eye(3)

    # Per-planet block (6x6)
    q_block = sigma_a ** 2 * np.block([
        [(dt ** 4) / 4 * I3, (dt ** 3) / 2 * I3],
        [(dt ** 3) / 2 * I3, (dt ** 2) * I3]
    ])

    # Full block diagonal
    Q = np.kron(np.eye(n_planets), q_block)
    return Q

# -------------------------
# Set up truth + filter sims (Sun + Earth + Jupiter)
# -------------------------
step=-2 * np.pi * 0.035
sim_true = rebound.Simulation()
sim_true.dt = step
sim_true.units = ('AU', 'yr', 'Msun')
sim_true.add(m=1.0)
sim_true.add(m=3e-6, a=1.0, e=0.0167)   # Earth (particle index 1)
sim_true.add(m=9.5e-4, a=5.2, e=0.0489) # Jupiter (index 2)
sim_true.move_to_com()

sim_est = rebound.Simulation()
sim_est.dt = step
sim_est.units = ('AU', 'yr', 'Msun')
sim_est.add(m=1.0)
sim_est.add(m=3e-6, a=1.0, e=0.0168)   # initial error in Earth
sim_est.add(m=9.5e-4, a=5.2, e=0.05) # initial error in Jupiter
sim_est.move_to_com()

# Which particles make the filter state? (skip Sun=0)
planet_indices = [1, 2]          # Earth, Jupiter
state_size = 6 * len(planet_indices)

ecc_true_lst = []
ecc_est_lst = []
meas_lst = []
meas_times = []
times = []

np.random.seed(5)
# -------------------------
# EKF initialization
# -------------------------
x_hat = get_state(sim_est, planet_indices)   # filter's current state
P = np.eye(state_size) * 1e-8  #  0 on off-diagonals
Q = np.eye(state_size)   # process noise for each state component (tunable)
sigma_a = 1e-10    # standard deviation of acceleration for Q matrix Au/yr**2
R = np.array([[1E-6]])          # measurement noise variance (eccentricity)

dt = step   # EKF step (years); local F will be computed over this dt
Nsteps = 302
print(f"{'t':>6} {'e_true':>10} {'z_meas':>10} {'e_est':>10} {'e_pred':>10} {'innov':>12}")

# -------------------------
# EKF loop: uses local F each step
# -------------------------
for step in range(Nsteps):
    t_next = (step + 1) * dt

    times.append(t_next)

    # --- propagate truth to t_next and get measurement ---
    sim_true.integrate(t_next)
    e_true = get_earth_ecc(sim_true, earth_index=1)
    ecc_true_lst.append(e_true)



    # --- compute local F around current estimate state ---
    # Use sim_est current state (not yet integrated to t_next) to compute F = d x(t+dt)/d x(t)
    F_local = compute_local_F(sim_est, planet_indices, dt)  # shape (state_size,state_size)

    # --- time update: propagate estimate forward by dt (mean) ---
    sim_est.integrate(t_next)           # advance filter sim to t_next
    x_pred = get_state(sim_est, planet_indices)

    Q = planet_process_noise(dt, sigma_a, n_planets=2)

    # propagate covariance with local F
    P = F_local @ P @ F_local.T + Q

    if (step % 20 == 0) or step == 1:
        z_meas = e_true + np.random.normal(0, np.sqrt(R))
        meas_lst.append(z_meas[0, 0])
        meas_times.append(t_next)

        # --- measurement prediction and analytic H ---
        e_pred = get_earth_ecc(sim_est, earth_index=1)
        H = de_dx_row(sim_est, earth_index=1, planet_indices=planet_indices)  # shape (1, state_size)

        # --- Kalman update ---
        y = np.array([[z_meas - e_pred]])  # innovation (1x1)
        S = H @ P @ H.T + R               # (1x1)
        K = P @ H.T @ np.linalg.inv(S)    # (state_size x 1)
        x_hat = x_pred + (K.flatten() * float(y))
        P = (np.eye(state_size) - K @ H) @ P
    else:
        x_hat = x_pred

    # --- inject updated state back into sim_est for next iteration ---
    set_state(sim_est, planet_indices, x_hat)

    e_est = get_earth_ecc(sim_est, earth_index=1)
    ecc_est_lst.append(e_est)


    # log
    #if step % 20 == 0:
#    print(f"{t_next:6.2f} {e_true:10.6f} {z_meas[0,0]:10.6e} {e_est: 10.6f} {e_pred:10.6f} {float(y):12.6e}")


plt.figure(1, figsize=(16, 6))
plt.plot(times, ecc_true_lst, label="true")
plt.plot(times, ecc_est_lst, label='est')
plt.plot(meas_times, meas_lst, label='meas')

# 3.2 Plot Laskar and/or Zeebe's models ========
# ZB20a = pd.read_csv('./ZB20a.csv').values  # two colums, time and ecc
#    ZB20a=pd.read_csv('/home/wuyujingwzt/PycharmProjects/Rebound/test3_HMatrix/ZB20a.csv').values
#    plt.plot(ZB20a[:, 0], ZB20a[:, 1], label='ZB20a')
#    plt.xlim([tKyr, 0])  # Change the xlim if needed.
# plt.title(title)
plt.ylabel('Eccentricity')
plt.legend(loc='best')

figname = "Fig"
plt.savefig(figname, dpi=300)
plt.show( )