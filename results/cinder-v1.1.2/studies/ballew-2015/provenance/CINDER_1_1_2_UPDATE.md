# CINDER 1.1.2 benchmark migration

This directory is the CINDER 1.1.2 rerun of the existing Ballew 2015
model-to-model benchmark. The literature source, digitized traces,
reconstruction assumptions, controller interpretation, and comparison metrics
are unchanged. No Ballew parameter is re-fit for this release.

The only intended migration is the CINDER mechanics version:

- distribution: `cinder-cvt==1.1.2`;
- source tag: `cinder-v1.1.2`;
- tag commit: `7637a38b4fb9ec21dfb953c1c80a27ec5f389654`.

CINDER 1.1.2 contains two energy-consistency corrections made after the original
1.0.0 benchmark results were frozen:

1. belt-wrap radial kinetic modes are retained in finite-speed hybrid
   capture/stop projections;
2. a helix-equipped reduced contact uses the power-equivalent representative
   pulley surface speed implied by the configured fixed/movable face torque
   split.

The Ballew reconstruction uses no helical secondary torque-reaction law, so the
second correction does not directly alter its reconstructed secondary contact.
The first can affect finite-speed stop/capture transitions and therefore the
benchmark must be regenerated rather than copying old artifacts.

The comparison remains a **model-to-model benchmark**, not experimental
validation. Fresh artifacts under this release directory are authoritative for
CINDER 1.1.2.
