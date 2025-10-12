# The CycloAstro Project

A hybrid Python and C computational framework for simulating, visualizing, and analyzing celestial dynamics.  
Combines the scientific flexibility of Python (Rebound, Astropy, NumPy, Matplotlib) with the speed and control of C for intensive orbital mechanics calculations.

---

## Project Overview

The CycloAstro Project aims to model and visualize complex gravitational interactions such as planetary systems, resonances, and orbital stability, while maintaining modularity for research extensions.

### Core Goals
- Build a performant orbital simulation engine in C
- Integrate seamlessly with Python and Rebound for analysis and plotting
- Provide reproducible, open-source tools for astrophysical research and teaching
- Establish a well-documented, version-controlled workflow

---

## Repository Structure

The CycloAstro Project/
├── cycloastro_c/              # Low-level C modules
│   └── src/
│       └── main.c
├── cycloastro_python/         # High-level Python scripts and analyses
│   └── orbit_sim.py
├── data/                      # Simulation or observational data
├── .vscode/                   # VS Code run/debug configs
├── Makefile_CycloAstro        # C build automation
├── PROJECT_SCOPE.md           # Scope and deliverables
└── README.md                  # You are here

---

## Environment Setup

### Step 1. Create Conda Environment
```bash
conda create -n cycloastro python=3.11 -y
conda activate cycloastro

conda install numpy matplotlib astropy -y
pip install rebound

python -c "import numpy, matplotlib, astropy, rebound; print('CycloAstro environment ready!')"

make -f Makefile_CycloAstro run

Welcome to The CycloAstro Project — C module initialized!


