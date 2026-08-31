# Static geometry study API

The geometry study layer solves and evaluates pulley/belt geometry independently
of time integration.

## Solve from endpoint radii

```python
from cinder.studies import (
    EndpointRadiiDesignRequest,
    solve_geometry_from_endpoint_radii,
)

design = solve_geometry_from_endpoint_radii(
    EndpointRadiiDesignRequest(
        context=context,
        primary_outer_radius_at_zero_shift=...,
        secondary_outer_radius_at_zero_shift=...,
    )
)
```

## Solve from target ratios

```python
from cinder.studies import (
    TargetRatioDesignRequest,
    solve_geometry_from_target_ratios,
)

design = solve_geometry_from_target_ratios(
    TargetRatioDesignRequest(
        context=context,
        maximum_ratio=...,
        minimum_ratio=...,
    )
)
```

With fixed active primary radial travel, the target-ratio route performs the
required scalar solve and raises `GeometryDesignInfeasibleError` when the
requested geometry cannot be satisfied.

## Evaluate a resolved design

```python
from cinder.studies import (
    evaluate_geometry_feasibility,
    evaluate_radius_plane,
    evaluate_ratio_sensitivity_field,
    sample_geometry_path,
    summarize_geometry_design,
)

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

The radius plane reports effective-radius ratio and implied belt outer length.
The sensitivity field reports `dR/ds` for active axial shift. Callers can
combine those independent fields with the sampled physical path as needed.
