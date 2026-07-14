#!/usr/bin/env bash
set -euo pipefail

baja-track validate-definitions examples/obstacle_event_definitions_CLEANED.csv
baja-track full-run \
  --gps examples/reference_run_gps.csv \
  --definitions examples/obstacle_event_definitions_CLEANED.csv \
  --config examples/config.example.toml \
  --output results/reference_full_run
