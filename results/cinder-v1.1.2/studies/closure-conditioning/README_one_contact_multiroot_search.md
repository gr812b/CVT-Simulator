# True one-contact multiroot / fold search

This patch is for the **actual 1D mixed contact branches**, not the earlier
1D visualization of the two-contact stick-stick manifold.

It searches:

```text
primary slip / secondary stick
    lambda_p = +/- mu_k,p
    solve R_s(lambda_s) = 0

primary stick / secondary slip
    lambda_s = +/- mu_k,s
    solve R_p(lambda_p) = 0
```

For every trial sticking lambda the inner CINDER closure is still the same unique
fixed-lambda 8x8 mechanical solve. The question is whether the resulting scalar
sticking residual has more than one zero in the physically admissible static
interval.

## Main command

From `results/cinder-v1.1.2`:

```powershell
python .\studies\closure-conditioning\search_one_contact_multiroot_folds.py `
  --global-search-dir .\studies\closure-conditioning\artifacts\global-comfortable-multiroot-search `
  --reference-path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
  --reference-frame 60 `
  --workers -1 `
  --lambda-samples 241 `
  --fixed-torque-samples 41 `
  --gif-frames 84
```

This is intended to be a substantial search. It scans every unique frozen state
available in the global-search candidate tables, all four mixed branch/direction
policies, both choices of varied shaft torque, and a wide fixed-torque grid.

## Why it is reasonably efficient

For one branch and one frozen state,

```text
R(lambda; Tp, Ts) = R0(lambda) + Gp(lambda) Tp + Gs(lambda) Ts
```

because external shaft torques enter the fixed-lambda mechanical closure
affinely. The script therefore spends the expensive work on three mechanical
evaluations per lambda sample, then explores many torque slices algebraically.

## Outputs

```text
one-contact-multiroot-fold-search/
  states_scanned.csv
  all_one_contact_fold_candidates.csv
  top_candidates.csv
  best_by_branch.csv
  summary.json

  best/
    best_candidate.json
    curve.csv
    branch_physics.csv

    required_torque_fold.png
    scalar_residual_two_roots.png
    branch_physics.png

    one_contact_fold_birth.gif
    one_contact_fold_interactive.html
```

The GIF is the key visual. It has two panels:

1. required varied shaft torque vs the remaining sticking lambda,
2. the **actual scalar sticking residual** vs that lambda.

As the torque level crosses a fold you should see:

```text
0 scalar roots -> one tangent/double root -> 2 scalar roots
```

if such a physically admissible case exists.

## Interpretation

A positive result means that the one-contact branch itself is globally
multivalued: the sliding contact has a unique prescribed kinetic lambda, but
there are two different admissible static lambdas at the remaining sticking
contact that close its acceleration residual.

A null result is also useful. It would support the stronger empirical statement
that, over the searched operating envelope, the mixed branches remain globally
single-root even though the stick-stick closure can fold.
