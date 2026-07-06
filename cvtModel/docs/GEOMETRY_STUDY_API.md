# CINDER static geometry study API

The static geometry study layer is intentionally separate from simulation and plotting:

```text
Case A / Case B solve -> ResolvedGeometryDesign
ResolvedGeometryDesign -> independent path, field, and feasibility evaluations
```

## Case A

```python
solve_geometry_from_endpoint_radii(
    EndpointRadiiDesignRequest(
        context=context,
        primary_outer_radius_at_zero_shift=...,
        secondary_outer_radius_at_zero_shift=...,
    )
)
```

The existing `BeltPulleyGeometrySpec` construction performs the belt-length
closure and computes the opposite endpoint.

## Case B

```python
solve_geometry_from_target_ratios(
    TargetRatioDesignRequest(
        context=context,
        maximum_ratio=...,
        minimum_ratio=...,
    )
)
```

With CINDER's fixed active primary radial travel, Case B is one scalar solve
and returns one valid design or raises `GeometryDesignInfeasibleError`. The
implementation scans the physical interval before refining the scalar root, so
it verifies the expected unique root rather than assuming one.

## Independent downstream evaluators

```python
summary = summarize_geometry_design(design)
path = sample_geometry_path(design, sample_count=301)
report = evaluate_geometry_feasibility(design)

plane = evaluate_radius_plane(
    belt=design.geometry_spec.belt,
    center_distance=design.center_distance,
    primary_outer_radius=primary_axis,
    secondary_outer_radius=secondary_axis,
)

sensitivity = evaluate_ratio_sensitivity_field(
    belt=design.geometry_spec.belt,
    center_distance=design.center_distance,
    sheave_half_angle=design.geometry_spec.sheave_half_angle,
    primary_outer_radius=primary_axis,
    secondary_outer_radius=secondary_axis,
)
```

The radius plane returns effective-radius ratio and implied belt outer length
for a selected center distance. Constant contours of the latter are the
constant-belt-length families.

The sensitivity field returns `dR/ds` in ratio per metre and ratio per
millimetre of **active** axial shift. It has no selected-path data; callers
compose it with the independently sampled path.

A project-local geometry smoke script can call these functions and plot the
returned fields, but plotting and launch tooling belong outside `src/cinder`.
