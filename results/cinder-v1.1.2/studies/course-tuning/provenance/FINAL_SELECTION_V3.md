# Final Section 4.5 selection revision 3

Revision 3 fixes the final Section 4.5 case set used by the common-course study. The selected fleet includes the admissible R26B7 ramp replacement and the D02 repair/over-correction cases needed for the severe-hill mechanism comparison.

`RC28` is not a final simulation case. The user's frozen CINDER 1.1.2 Results environment rejected RC28 during the released fixed-pivot construction audit because the selected contact branch was not valid across the full declared operating interval. `R26B7` retains the first 10 mm of the reference ramp, uses a 7 mm C3 blend, and finishes with an arc tail at 26 degrees. In the frozen-environment replacement campaign it passed the released geometry audit with 513/513 traced positions, maximum mathematical candidates = 1, no findings, and completed the unchanged 732 m course.

The D02 family is retained as a mechanism-resolved hill comparison. D02 uses 65% replaceable tip mass with 115% primary preload. D02_M restores the reference tip mass while retaining that preload, and D02_P restores the reference primary preload while retaining the light tips. D02_M150 retains D02's 115% primary preload but increases the replaceable tip mass to 150% of reference. All corresponding flyweight mass moments are updated by the common physical tune resolver.

The D02_M150 definition was checked in the user's frozen Results environment in campaign `unified38_c6a32w12_h18hold240__tight__a625698e273b` (fingerprint `a625698e273bef933ad8ce400eb1dabacab3d4cf164aefe69692024437a1819e`). The case completed the 732 m course with no inspection error or sampled review flag. On the main 38-degree hill it reached the low-ratio seat near 171.132 m and released it near 173.041 m with reason `low_ratio_seat_released_by_tensile_reaction`, providing the selected high-primary-force comparison without imposing that outcome in the final runner.

The final common-course fleet is:

`R00, W85, P300, RC10, R26B7, RC40L, H28, U55, D01, D02, D02_M, D02_M150, D02_P`.

The supporting 800 m flat remains `R00` and `U55`. The road, initial conditions, shaft boundaries, belt/contact model, bilateral/slotted helix policy, and final tight numerical settings are common to the selected cases.
