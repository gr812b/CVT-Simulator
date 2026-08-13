# Superseded v9 boundary-derivative failure

These partial runs are retained only to reproduce the implementation defect documented in
`../../SINGULARITY_DIAGNOSIS.md`. They are not CINDER-vs-Ballew physical comparison results.
The exact rank deficiency was caused by deadzone-side geometry derivatives being used for an
engaged event-localization stage at the low-ratio boundary.
