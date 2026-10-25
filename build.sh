#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Generating Machine Learning Model Artifact..."
python train_model.py

echo "==> Render Build Completed Successfully."
