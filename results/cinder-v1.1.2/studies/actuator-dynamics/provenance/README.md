# Provenance

The CINDER mechanics implementation is the published `cinder-cvt==1.1.2`
package.

The existing baseline ablation and coupling-energy utilities are materialized
from the frozen `cinder-v1.1.2` tag and checked against the Git blob SHAs in
`../upstream_manifest.json`.

The new equation-derived validity envelopes and controlled-transient selection
logic are release-scoped study code stored directly in this directory. They do
not modify CINDER mechanics.

The broad exploratory stress-search and movable-inertia/torque scaling scripts
from `launchTools` are deliberately not part of this official study.
