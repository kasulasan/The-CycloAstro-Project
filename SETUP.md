# CycloAstro Project — Environment Setup Guide

This guide ensures anyone can recreate the full CycloAstro Project environment — including Python, C, and C++ modules — on their own machine.

---

## 1. Clone the Repository

git clone https://github.com/kasulasan/The-CycloAstro-Project.git
cd The-CycloAstro-Project

---

## 2. Create the Conda Environment

The project uses a lightweight, cross-platform Conda environment that works on macOS, Linux, and Windows.

Run the following commands:

conda env create -f environment.yml
conda activate cycloastro

This installs the required scientific stack:
- Python 3.11  
- NumPy  
- Matplotlib  
- Astropy  
- Rebound  
- PyBind11  
- (plus pip for optional extras)

---

## 3. Verify the Installation

After activation, confirm that everything loads correctly:

python -c "import numpy, matplotlib, astropy, rebound; print('CycloAstro environment OK')"

Expected output:

CycloAstro environment OK

---

## 4. Rebuild or Update the Environment (Optional)

If you add new dependencies, export an updated environment file and push it to the repository:

conda env export --no-builds | grep -v "prefix" > environment.yml
git add environment.yml
git commit -m "Update environment with new dependencies"
git push

---

## 5. Platform Notes

### macOS / Linux
Ensure build tools are installed:

# macOS
xcode-select --install

# Ubuntu / Debian
sudo apt update && sudo apt install build-essential -y

Then run the C module:

make -f Makefile_CycloAstro run

---

### Windows
1. Install Anaconda from https://www.anaconda.com/download  
2. Install MinGW-w64 from https://winlibs.com/ and add it to your PATH:  

set PATH=C:\mingw64\bin;%PATH%

3. Verify the compiler:  

g++ --version

4. Compile and run the simulation:  

g++ cycloastro_c/src/main.c -o cycloastro_sim.exe
.\cycloastro_sim.exe

Expected output:

Welcome to The CycloAstro Project — C module initialized!

---

## 6. Verification

Once both components run successfully, confirm the full setup:

python cycloastro_python/orbit_sim.py

This runs the Python orbital simulation using the Rebound engine and confirms integration between C and Python modules.

---

With this setup, the CycloAstro Project can be built and executed reproducibly on any supported platform.
