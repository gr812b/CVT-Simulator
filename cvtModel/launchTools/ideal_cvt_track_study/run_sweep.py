from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Sequence

from metrics import compare_to_reference, summarize_trace
from models import (
    DriverModel,
    EngineModel,
    INCH_TO_METRE,
    IdealCVTModel,
    SimulationSettings,
    TireModel,
    VehicleModel,
)
from simulation import StudyCase, run_simulation
from track_builder import Track

HERE = Path(__file__).resolve().parent
DEFAULT_TRACK = HERE / "tracks" / "lot_m.json"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep ideal bounded-CVT ratio limits, final-drive ratio, and tire radius "
            "on a distance-defined track. This does not import CINDER."
        )
    )
    parser.add_argument("--track", type=Path, default=DEFAULT_TRACK)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ideal_cvt_track_study/lot_m_sweep"))
    parser.add_argument("--minimum-cvt-ratios", type=float, nargs="+", default=[0.90, 1.1306679708652254, 1.35])
    parser.add_argument("--maximum-cvt-ratios", type=float, nargs="+", default=[4.20, 4.923076923076923, 5.80])
    parser.add_argument("--final-drive-ratios", type=float, nargs="+", default=[6.25, 7.00, 7.556, 8.50])
    parser.add_argument("--wheel-radii-in", type=float, nargs="+", default=[10.0, 11.0, 12.0])
    parser.add_argument(
        "--independent-variable",
        choices=(
            "minimum_speed_ratio",
            "maximum_speed_ratio",
            "final_drive_ratio",
            "wheel_radius_in",
        ),
        default="final_drive_ratio",
        help=(
            "Parameter placed on the x-axis of sweep sensitivity plots. "
            "Other swept dimensions remain visible as background points, while the "
            "baseline configuration is connected as a line."
        ),
    )
    parser.add_argument("--vehicle-mass-kg", type=float, default=300.0)
    parser.add_argument("--tire-slip-stiffness", type=float, default=2500.0)
    parser.add_argument(
        "--maximum-time-s",
        type=float,
        default=None,
        help="Maximum simulation time. Default scales automatically with track length.",
    )
    parser.add_argument("--integration-step-s", type=float, default=0.01)
    parser.add_argument("--report-step-s", type=float, default=0.05)
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Parallel worker processes. 0 chooses up to 8 automatically; 1 runs sequentially.",
    )
    parser.add_argument("--no-show", action="store_true")
    return parser.parse_args(argv)


def _write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    scalar_keys: list[str] = []
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (str, int, float, bool)) and key not in scalar_keys:
                scalar_keys.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=scalar_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _run_one_case(payload: tuple[Any, ...]) -> tuple[int, dict[str, Any]]:
    (
        index,
        track,
        engine,
        vehicle,
        driver,
        settings,
        tire_slip_stiffness,
        minimum_ratio,
        maximum_ratio,
        final_drive,
        wheel_radius_in,
        reference_summary,
    ) = payload
    tire = TireModel(
        wheel_radius_m=wheel_radius_in * INCH_TO_METRE,
        slip_stiffness_n_per_mps=tire_slip_stiffness,
    )
    cvt = IdealCVTModel(
        minimum_speed_ratio=minimum_ratio,
        maximum_speed_ratio=maximum_ratio,
        final_drive_ratio=final_drive,
    )
    case_name = (
        f"q {minimum_ratio:.3f}-{maximum_ratio:.3f}, "
        f"G {final_drive:.3f}, tire {wheel_radius_in:.2f} in"
    )
    case = StudyCase(
        name=case_name,
        engine=engine,
        vehicle=vehicle,
        tire=tire,
        cvt=cvt,
        driver=driver,
        infinite_cvt=False,
    )
    trace = run_simulation(case=case, track=track, settings=settings)
    summary = compare_to_reference(
        summarize_trace(trace, target_engine_rpm=engine.peak_power_rpm, ideal_peak_power_w=engine.peak_power_w),
        reference_summary,
    )
    summary.update(
        {
            "minimum_speed_ratio": minimum_ratio,
            "maximum_speed_ratio": maximum_ratio,
            "ratio_range": maximum_ratio / minimum_ratio,
            "final_drive_ratio": final_drive,
            "wheel_radius_in": wheel_radius_in,
            "wheel_radius_m": wheel_radius_in * INCH_TO_METRE,
        }
    )
    return int(index), summary


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    track = Track.from_json(args.track)
    engine = EngineModel.baja_br10()
    vehicle = VehicleModel(mass_kg=args.vehicle_mass_kg)
    driver = DriverModel()
    maximum_time_s = (
        args.maximum_time_s
        if args.maximum_time_s is not None
        else max(180.0, track.length_m / 4.0)
    )
    settings = SimulationSettings(
        maximum_time_s=maximum_time_s,
        integration_step_s=args.integration_step_s,
        report_step_s=args.report_step_s,
    )
    combinations = [
        combo
        for combo in itertools.product(
            args.minimum_cvt_ratios,
            args.maximum_cvt_ratios,
            args.final_drive_ratios,
            args.wheel_radii_in,
        )
        if combo[0] < combo[1]
    ]
    worker_count = args.workers
    if worker_count == 0:
        worker_count = min(8, max(1, (os.cpu_count() or 2) - 1))
    if worker_count < 1:
        raise ValueError("workers must be non-negative")

    print(f"Track: {track.name} ({track.length_m:.1f} m)")
    print(f"Running {len(combinations)} bounded-CVT combinations with {worker_count} worker(s)")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference_by_wheel_radius: dict[float, dict[str, Any]] = {}
    reference_final_drive = float(args.final_drive_ratios[0])
    reference_minimum_ratio = float(args.minimum_cvt_ratios[0])
    reference_maximum_ratio = float(args.maximum_cvt_ratios[0])
    for wheel_radius_in in sorted(set(args.wheel_radii_in)):
        tire = TireModel(
            wheel_radius_m=wheel_radius_in * INCH_TO_METRE,
            slip_stiffness_n_per_mps=args.tire_slip_stiffness,
        )
        cvt = IdealCVTModel(
            minimum_speed_ratio=reference_minimum_ratio,
            maximum_speed_ratio=reference_maximum_ratio,
            final_drive_ratio=reference_final_drive,
        )
        reference_case = StudyCase(
            name=f"Infinite reference {wheel_radius_in:.2f} in",
            engine=engine,
            vehicle=vehicle,
            tire=tire,
            cvt=cvt,
            driver=driver,
            infinite_cvt=True,
        )
        reference_trace = run_simulation(case=reference_case, track=track, settings=settings)
        reference_by_wheel_radius[wheel_radius_in] = summarize_trace(
            reference_trace,
            target_engine_rpm=engine.peak_power_rpm,
            ideal_peak_power_w=engine.peak_power_w,
        )

    payloads = [
        (
            index,
            track,
            engine,
            vehicle,
            driver,
            settings,
            args.tire_slip_stiffness,
            minimum_ratio,
            maximum_ratio,
            final_drive,
            wheel_radius_in,
            reference_by_wheel_radius[wheel_radius_in],
        )
        for index, (
            minimum_ratio,
            maximum_ratio,
            final_drive,
            wheel_radius_in,
        ) in enumerate(combinations, start=1)
    ]

    indexed_rows: dict[int, dict[str, Any]] = {}
    if worker_count == 1:
        iterator = (_run_one_case(payload) for payload in payloads)
        for index, summary in iterator:
            indexed_rows[index] = summary
            print(
                f"[{index:03d}/{len(combinations):03d}] "
                f"q={summary['minimum_speed_ratio']:.3f}-{summary['maximum_speed_ratio']:.3f}, "
                f"G={summary['final_drive_ratio']:.3f}, r={summary['wheel_radius_in']:.1f} in "
                f"-> {summary['lap_time_s']:.2f} s, "
                f"loss={summary['finite_ratio_opportunity_loss_average_power_hp']:.2f} hp avg",
                flush=True,
            )
    else:
        with ProcessPoolExecutor(
            max_workers=worker_count,
            mp_context=get_context("spawn"),
        ) as executor:
            futures = [executor.submit(_run_one_case, payload) for payload in payloads]
            completed_count = 0
            for future in as_completed(futures):
                index, summary = future.result()
                indexed_rows[index] = summary
                completed_count += 1
                print(
                    f"[{completed_count:03d}/{len(combinations):03d}] "
                    f"q={summary['minimum_speed_ratio']:.3f}-{summary['maximum_speed_ratio']:.3f}, "
                    f"G={summary['final_drive_ratio']:.3f}, r={summary['wheel_radius_in']:.1f} in "
                    f"-> {summary['lap_time_s']:.2f} s, "
                    f"loss={summary['finite_ratio_opportunity_loss_average_power_hp']:.2f} hp avg",
                    flush=True,
                )

    rows = [indexed_rows[index] for index in sorted(indexed_rows)]
    _write_summary_csv(args.output_dir / "sweep_summary.csv", rows)
    (args.output_dir / "sweep_summary.json").write_text(
        json.dumps(
            {
                "track": track.to_dict(),
                "engine_peak_power_rpm": engine.peak_power_rpm,
                "engine_peak_power_w": engine.peak_power_w,
                "workers": worker_count,
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ranked = sorted(
        (row for row in rows if bool(row["completed"])),
        key=lambda row: float(row["lap_time_s"]),
    )
    (args.output_dir / "top_20.json").write_text(
        json.dumps(ranked[:20], indent=2), encoding="utf-8"
    )
    from plotting import plot_sweep

    plot_paths = plot_sweep(
        rows=rows,
        output_dir=args.output_dir,
        independent_variable=args.independent_variable,
        baseline_minimum_ratio=1.1306679708652254,
        baseline_maximum_ratio=4.923076923076923,
        baseline_final_drive=7.556,
        baseline_wheel_radius_m=11.0 * INCH_TO_METRE,
        show=not args.no_show,
    )

    if ranked:
        best = ranked[0]
        print("\nBest completed configuration")
        print(
            f"  q={best['minimum_speed_ratio']:.4f}-{best['maximum_speed_ratio']:.4f}, "
            f"G={best['final_drive_ratio']:.3f}, tire={best['wheel_radius_in']:.2f} in"
        )
        print(f"  lap time: {best['lap_time_s']:.3f} s")
        print(
            "  average opportunity-loss power: "
            f"{best['finite_ratio_opportunity_loss_average_power_hp']:.3f} hp"
        )
        print(f"  outside engine band: {best['time_outside_target_rpm_band_s']:.2f} s")
    print(f"\nWrote {len(rows)} rows and {len(plot_paths)} plots to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
