# Final Section 4.5 selection revision 3

Revision 3 changes one vehicle definition from revision 2: `RC28` is replaced one-for-one by `R26B7`.

The user's frozen CINDER 1.1.2 Results environment rejected RC28 during the released fixed-pivot construction audit because the selected contact branch was not valid across the full declared operating interval. RC28 is therefore not a final simulation case.

`R26B7` retains the first 10 mm of the reference ramp, uses a 7 mm C3 blend, and finishes with an arc tail at 26 degrees. In the frozen-environment replacement campaign it passed the released geometry audit with 513/513 traced positions, maximum mathematical candidates = 1, no findings, and completed the unchanged 732 m course.

No other selected vehicle, road feature, boundary, initial condition, or numerical setting changes in revision 3. The final fleet is:

`R00, W85, P300, RC10, R26B7, RC40L, H28, U55, D01, D02, D02_M, D02_P`.

The supporting 800 m flat remains `R00` and `U55`.
