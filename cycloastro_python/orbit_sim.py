import rebound
import matplotlib.pyplot as plt

# Initialize a new simulation
sim = rebound.Simulation()
sim.add(m=1.0)        # Star
sim.add(m=1e-3, a=1.0)  # Planet 1
sim.add(m=1e-3, a=1.5)  # Planet 2

# Integrate forward in time
sim.integrate(1000)

# Extract particle positions
x = [p.x for p in sim.particles]
y = [p.y for p in sim.particles]
labels = ["Star", "Planet 1", "Planet 2"]

# Plot with Matplotlib
fig, ax = plt.subplots()
ax.scatter(x[0], y[0], color="yellow", s=150, label=labels[0])
ax.scatter(x[1], y[1], color="blue", s=50, label=labels[1])
ax.scatter(x[2], y[2], color="green", s=50, label=labels[2])

ax.set_aspect("equal")
ax.set_xlabel("x [AU]")
ax.set_ylabel("y [AU]")
ax.set_title("CycloAstro Orbital Simulation Test")
ax.legend()
plt.show()