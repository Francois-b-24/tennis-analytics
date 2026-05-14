"""Configuration pytest (limite de parallélisme numérique pour éviter les blocages)."""

from __future__ import annotations

import os

# Réduit les risques de hang avec OpenBLAS / MKL sur certains macOS + sklearn.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
