"""Rendering projections of retained CINDER contact resultants.

No closure is solved here. N is the two-face integrated normal load; each movable
face receives half. The wrap pressure follows CINDER's analytical tension field:
T = C + n sin(beta), with C fixed by integral(n dtheta) = N. Gaussian quadrature
integrates the displayed sectors. Roller reactions use CINDER's selected contact
normal; helix reactions use its local dtheta/dx and reported dynamic force terms.
Missing channels remain missing, never silently zero-filled.
"""

import math

import numpy as np

from app.schemas.scene import ForcePlayback, ForceTrack, ForceVectorSample


def project_forces(result, scene, tension):
    table = result["report_table"]
    columns = {c["key"]: c["values"] for c in table["columns"]}
    times = columns[table["axis_key"]]
    indices = list(range(len(times)))
    tracks = []
    notes = [
        "Forces act on the selected movable assembly. Positive axial closes its pulley; radial points outwards; tangential follows positive shaft rotation.",
        "Belt arrows are integrated wrap sectors on one face; roller arrows are individual contacts. Springs show their assembly resultant.",
        "Normal load is shared equally between belt faces. Torque sharing follows the assembly's helical element, or an equal split for a rigidly guided pulley.",
        "Shaft/bearing, primary torque-guide and travel-stop reactions are not reported. This is a contact-force view, not a complete equilibrium diagram.",
    ]
    # Bound the optional visualization payload. Preserve contact-validity edges
    # so interpolation never bridges a missing/unsupported contact interval.
    if len(times) > 2000:
        indices = set(np.linspace(0, len(times) - 1, 2000, dtype=int).tolist())
        # CINDER records both sides of discrete events at the same timestamp.
        # Keep both rows so a pinned replay frame selects the correct side.
        for i in range(1, len(times)):
            if times[i] == times[i - 1]:
                indices.update((i - 1, i))
        for key in ("contact.primary_lambda", "contact.secondary_lambda"):
            values = columns.get(key, [])
            valid = [isinstance(v, (int, float)) and math.isfinite(v) for v in values]
            for i in range(1, len(valid)):
                if valid[i] != valid[i - 1]:
                    indices.update((i - 1, i))
        indices = sorted(indices)
        columns = {key: [values[i] for i in indices] for key, values in columns.items()}
        times = columns[table["axis_key"]]
        notes.append(
            "Arrows interpolate a reduced set of retained frames, preserving contact gaps. Plots and exports retain every recorded sample."
        )
    poses = scene.mechanisms.poses if scene.mechanisms else []
    shifts = np.array([p.shift_m for p in poses])
    pose_cache = {}

    def torque_share(body):
        return getattr(scene.mechanisms, f"{body}_movable_torque_fraction", 0.5)

    def value(key, i):
        data = columns.get(key)
        v = data[i] if data is not None else None
        return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None

    def pose(i, field, component=None):
        shift = value("state.shift_position", i)
        if shift is None or not poses:
            return None
        key = (field, component)
        if key not in pose_cache:
            values = [getattr(p, field) for p in poses]
            pose_cache[key] = (
                None
                if any(v is None for v in values)
                else [v[component] if component is not None else v for v in values]
            )
        values = pose_cache[key]
        if values is None:
            return None
        return float(np.interp(shift, shifts, values))

    def track(key, label, body, anchor, samples, unit="N"):
        if any(v is not None for v in samples):
            tracks.append(
                ForceTrack(
                    key=key,
                    label=label,
                    body=body,
                    anchor=anchor,
                    samples=samples,
                    unit=unit,
                )
            )

    def sample(components, **kwargs):
        if any(v is None or not math.isfinite(v) for v in components):
            return None
        return ForceVectorSample(components=components, **kwargs)

    for body in ("primary", "secondary"):
        prefix = f"actuation.{body}."
        track(
            f"{body}.spring",
            "Axial spring",
            body,
            "spring",
            [
                sample((v, 0, 0))
                if (v := value(prefix + "axial_spring", i)) is not None
                else None
                for i in range(len(times))
            ],
        )
        track(
            f"{body}.belt_torque",
            "Belt torque on movable face",
            body,
            "shaft",
            [
                sample((v * torque_share(body), 0, 0))
                if (v := value(f"contact.{body}_transmitted_torque", i)) is not None
                else None
                for i in range(len(times))
            ],
            "N·m",
        )

    primary = scene.mechanisms.primary if scene.mechanisms else None
    if primary:
        fly_keys = [
            k
            for k in columns
            if k.startswith("actuation.primary.fixed_pivot_flyweight_")
        ]
        for j in range(primary.count):
            samples = []
            for i in range(len(times)):
                parts = [value(k, i) for k in fly_keys]
                nx, nr = (
                    pose(i, "primary_normal_axial_radial", 0),
                    pose(i, "primary_normal_axial_radial", 1),
                )
                axial = (
                    sum(parts) / primary.count if parts and None not in parts else None
                )
                radius, position = (
                    pose(i, "primary_contact_m", 1),
                    pose(i, "primary_contact_m", 0),
                )
                samples.append(
                    sample(
                        (axial, axial * nr / nx, 0),
                        phase_rad=j * 2 * math.pi / primary.count,
                        radius_m=radius,
                        axial_position_m=position,
                    )
                    if axial is not None
                    and nx is not None
                    and abs(nx) > 1e-10
                    and nr is not None
                    and radius is not None
                    and position is not None
                    else None
                )
            track(
                f"primary.ramp.{j}", f"Ramp contact {j + 1}", "primary", "ramp", samples
            )

    if scene.mechanisms and scene.mechanisms.secondary_helix_points_m:
        r = math.hypot(*scene.mechanisms.secondary_helix_points_m[0][:2])
        helix_keys = [k for k in columns if k.startswith("actuation.secondary.helix_")]
        # The scene depicts three equally spaced load-sharing tracks.
        for j in range(3):
            samples = []
            for i in range(len(times)):
                parts = [value(k, i) for k in helix_keys]
                h = pose(i, "secondary_helix_dtheta_dx")
                axial = sum(parts) / 3 if parts and None not in parts else None
                samples.append(
                    sample(
                        (axial, 0, -axial / (r * h)),
                        phase_rad=j * 2 * math.pi / 3,
                        radius_m=r,
                    )
                    if axial is not None and h is not None and abs(h) > 1e-10
                    else None
                )
            track(
                f"secondary.helix.{j}",
                f"Helix contact {j + 1}",
                "secondary",
                "helix",
                samples,
            )
        spring_torque = []
        for i in range(len(times)):
            force, h = (
                value("actuation.secondary.helix_torsional_preload", i),
                pose(i, "secondary_helix_dtheta_dx"),
            )
            spring_torque.append(
                sample((force / h, 0, 0))
                if force is not None and h is not None and abs(h) > 1e-10
                else None
            )
        track(
            "secondary.spring_torque",
            "Torsional spring",
            "secondary",
            "spring",
            spring_torque,
            "N·m",
        )

    # Integrate six displayed sectors using eight quadrature points per sector.
    nodes, weights = np.polynomial.legendre.leggauss(8)
    sectors = 6
    u = np.concatenate([(j + (nodes + 1) / 2) / sectors for j in range(sectors)])
    w = np.tile(weights / (2 * sectors), sectors)
    beta = scene.sheave_half_angle_rad
    for body in ("primary", "secondary"):
        sector_samples = [[] for _ in range(sectors)]
        expression = tension.regions[f"{body}_wrap"]
        for i in range(len(times)):
            n = value(f"contact.{body}_normal_resultant", i)
            lam = value(f"contact.{body}_lambda", i)
            wrap = value(f"geometry.{body}_wrap_angle", i)
            rp = value(f"geometry.{body}_effective_radius", i)
            phi_p = value("geometry.primary_wrap_angle", i)
            if None in (n, lam, wrap, rp, phi_p) or wrap <= 0:
                for samples in sector_samples:
                    samples.append(None)
                continue
            signals = {
                k: v if (v := value(k, i)) is not None else float("nan")
                for k in columns
            }
            tensile = np.asarray(expression.evaluate(coordinate=u, signals=signals))
            offset = float(np.sum(tensile * w)) - n * math.sin(beta) / wrap
            normal_density = (tensile - offset) / math.sin(beta)
            # Pressure below zero is not an admissible contact vector.
            if not np.all(np.isfinite(normal_density)) or np.min(
                normal_density
            ) < -1e-6 * max(1, abs(n)):
                for samples in sector_samples:
                    samples.append(None)
                continue
            alpha = (math.pi - phi_p) / 2
            start = (
                math.pi / 2 + alpha if body == "primary" else 3 * math.pi / 2 - alpha
            )
            for j in range(sectors):
                sl = slice(j * 8, (j + 1) * 8)
                phase = start + (j + 0.5) / sectors * wrap
                angle = start + u[sl] * wrap
                dn = normal_density[sl] * w[sl] * wrap / 2
                radial, tangential = (
                    -math.sin(beta) * dn,
                    -lam * dn * 2 * torque_share(body),
                )
                fx = np.sum(radial * np.cos(angle) - tangential * np.sin(angle))
                fy = np.sum(radial * np.sin(angle) + tangential * np.cos(angle))
                sector_samples[j].append(
                    sample(
                        (
                            -float(np.sum(dn)) * math.cos(beta),
                            float(fx * math.cos(phase) + fy * math.sin(phase)),
                            float(-fx * math.sin(phase) + fy * math.cos(phase)),
                        ),
                        phase_rad=phase,
                        radius_m=rp,
                    )
                )
        for j, samples in enumerate(sector_samples):
            track(f"{body}.belt.{j}", f"Belt sector {j + 1}", body, "belt", samples)
    return ForcePlayback(
        times_s=times, report_indices=indices, tracks=tracks, notes=notes
    )
