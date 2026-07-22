import os

# Anchored to this file's location instead of the current working directory —
# running the script from inside src/ (instead of the project root, as the
# README instructs) used to silently create a duplicate src/results/ folder
# because "results/..." was resolved relative to whatever directory the
# script happened to be launched from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR  = os.path.join(PROJECT_ROOT, "results")
