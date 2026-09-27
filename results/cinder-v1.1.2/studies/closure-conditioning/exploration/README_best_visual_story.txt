What is in this patch
---------------------
1. exploration/find_best_visual_multiroot_story.py
   Orchestrates the shortlist -> continuation -> manifold -> focused slice -> GIF pipeline.

2. analysis/make_fixed_torque_slice_visuals.py
   Rebuilds the focused slice artifacts, with the curve fixed so the first and last points are
   not spuriously wrapped together.

3. exploration/render_multiroot_story_gif.py
   Builds a compact explanatory GIF from one manifold directory.

Typical run
-----------
From results/cinder-v1.1.2:

  python .\studies\closure-conditioning\exploration\find_best_visual_multiroot_story.py `
    --global-search-dir .\studies\closure-conditioning\artifacts\global-comfortable-multiroot-search `
    --reference-path-csv .\studies\closure-conditioning\artifacts\controlled-free-shift-animation\expanded_res641_locked_locked_path\preflight_path.csv `
    --reference-frame 60 `
    --top-k 8 `
    --vary secondary `
    --frames 72 `
    --jobs 8

Outputs
-------
The master script writes to:

  studies\closure-conditioning\artifacts\best-visual-multiroot-story

Inside the chosen best candidate folder you should find:
  * continuation\candidate_...\vary_secondary_torque\...
  * manifold\...
  * story-gif\multiroot_story.gif

Quick rerender for one already-built manifold
---------------------------------------------

  python .\studies\closure-conditioning\analysis\make_fixed_torque_slice_visuals.py `
    --manifold-dir <manifold-dir>

  python .\studies\closure-conditioning\exploration\render_multiroot_story_gif.py `
    --manifold-dir <manifold-dir> --frames 72 --jobs 8
