# Closure conditioning

This study asks two different numerical questions and keeps them separate:

1. Is the fixed-\((\lambda_p,\lambda_s)\) **production 8×8 mechanical closure**
   full-rank and well conditioned?
2. Is the **2×2 stick-root map** locally well conditioned and effectively unique?

It loads only the release default:

```text
../../defaults/baja_reference_simulation_case.json
```

The mild load-disturbed reference is created as an explicit override in this
study's own `study.json`; no external launch-tool code is copied in.

For representative stick-stick states, the full run generates:

- physical static-capacity lambda maps;
- expanded signed maps;
- broad \([-10,10]^2\) structural maps;
- \(R_p\), \(R_s\), residual norm;
- raw and equilibrated 8×8 condition numbers;
- 8×8 rank;
- \(\sigma_{\min}(J_R)\), \(\sigma_{\max}(J_R)\), \(\kappa(J_R)\), \(\det J_R\);
- normal-resultant maps;
- multi-start root-basin/uniqueness tests;
- broad-domain slices through the physical root;
- a table locating the strongest conditioning / force-amplification features.

The broad maps are diagnostic only; they are not presented as physically
admissible traction regions.

Run from `results/cinder-v1.1.2`:

```powershell
python .\studies\closure-conditioning\run.py
```

Fast structural preview:

```powershell
python .\studies\closure-conditioning\run.py --quick
```
