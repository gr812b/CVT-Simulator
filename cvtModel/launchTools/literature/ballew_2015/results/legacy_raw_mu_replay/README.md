# Legacy raw-`mu` force replay

These files are retained only for provenance of the first successful Ballew comparison run.

They were generated before reconstruction item A10 was identified. In that run Ballew's published
`mu_s = 0.55` and `mu_k = 0.40` were copied directly into CINDER's reduced traction-utilization
limits. Ballew's node law instead applies `mu * F_Z`, while the corresponding CINDER reduced
radial resultant is `N = 2 F_clamp tan(beta)`. The corrected benchmark therefore uses
`lambda = mu / (2 tan(beta))`.

Do not use the metrics in this directory as the canonical Ballew comparison. They are intentionally
preserved to show the effect of the earlier convention mismatch.
