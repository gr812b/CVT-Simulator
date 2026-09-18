# Pre-redesign baseline run interpretation

The uploaded `cinder-v1.1.2` actuator baseline/coupling run was reviewed before
the official off-baseline study was designed.

Key observed values:

- full model time to full shift: 6.53125 s;
- QS-flyweight time to full shift: 6.51061 s;
- QS-helix time to full shift: 6.54004 s;
- fully-QS time to full shift: 6.51940 s;
- full-model transition count: 16;
- direct generalized shift mass: 6.8318 to 13.0972 kg;
- maximum flyweight reflected contribution: 0.57212 kg;
- maximum helix reflected contribution: 10.70475 kg.

The raw all-time same-state total-clamp corrections reached about 75.5 N
(primary) and 1003.6 N (secondary), but these maxima occur in the initial
engagement/capture window near 0.06 s and should not be presented as ordinary
continuous-operation magnitudes.

Using the mechanism-specific quasi-static forces as the denominator:

- max |Pi_fw| over the whole run: about 0.0534;
- max |Pi_h| over the whole run: about 0.451;
- after 0.10 s, max |Pi_fw|: about 1.47e-5;
- after 0.10 s, max |Pi_h|: about 7.51e-3.

Thus the baseline shows a clear result already: actuator inertia can be
material during rigid engagement/capture while the ordinary continuous launch
is close to quasi-static, particularly for the primary flyweight. The
secondary helix retains a small continuous correction.

Independent-trajectory differences are also small in the 10 s baseline. For
example, relative to the full model, approximate RMS primary-speed differences
were 2.6 rpm (QS flyweight), 2.1 rpm (QS helix), and 4.1 rpm (fully QS).

The helix nevertheless contributes a large raw diagonal generalized shift-mass
term. This is not contradictory: the CVT is a coupled shaft/shift system, so a
large direct M_ss contribution does not imply a proportionally large trajectory
difference. This is one reason the redesigned study reports both equation-level
dynamic numbers and independently integrated trajectory consequences.

Health assessment: no result in the uploaded run suggested a broken mechanism
implementation. The main issue was interpretive: all-time peak percentages can
be dominated by the short engagement/capture transient, and raw reflected-mass
magnitude is not a consequence metric.
