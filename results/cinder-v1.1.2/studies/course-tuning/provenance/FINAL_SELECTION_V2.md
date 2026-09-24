# Final Section 4.5 selection revision 2

The course is unchanged. The root final fleet is revised to add shift-curve-shape coverage without changing actuator model classes or shaft boundaries.

Promoted from exploration:

- `P300`: 3x primary spring rate with spring force matched at the low-ratio engagement geometry;
- `RC10`: early ramp reshape ending at 10 degrees;
- `RC28`: early ramp reshape ending at 28 degrees;
- `RC40L`: later-onset ramp reshape ending at 40 degrees.

Moved from the root selection back to exploration/supporting use:

- `W115`;
- `B01`.

The retained root cases remain `R00`, `W85`, `H28`, `U55`, `D01`, `D02`, `D02_M`, and `D02_P`.

The root report now includes an opening-flat shift-shape analysis that uses only engaged, freely shifting, stick-stick, positive-shift-rate samples from 15--85% active travel. Its slope/shape metrics are therefore not contaminated by clutch slip, structural-stop dwell, hill backshift, or descent.
