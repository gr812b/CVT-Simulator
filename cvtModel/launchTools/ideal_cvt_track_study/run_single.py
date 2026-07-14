from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

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
from plotting import plot_single_run
from simulation import StudyCase, run_simulation
from track_builder import Track

HERE = Path(__file__).resolve().parent
DEFAULT_TRACK = HERE / "tracks" / "lot_m.json"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one standalone bounded-perfect-CVT tire-slip lap and compare it "
            "with an unbounded infinite-CVT reference. This does not import CINDER."
        )
    )
    parser.add_argument("--track", type=Path, default=DEFAULT_TRACK)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ideal_cvt_track_study/lot_m_single"))
    parser.add_argument("--minimum-cvt-ratio", type=float, default=1.1306679708652254)
    parser.add_argument("--maximum-cvt-ratio", type=float, default=4.923076923076923)
    parser.add_argument("--final-drive-ratio", type=float, default=7.556)
    parser.add_argument("--wheel-radius-in", type=float, default=11.0)
    parser.add_argument("--vehicle-mass-kg", type=float, default=300.0)
    parser.add_argument("--tire-slip-stiffness", type=float, default=2500.0)
    parser.add_argument(
        "--maximum-time-s",
        type=float,
        default=None,
        help="Maximum simulation time. Default scales automatically with track length.",
    )
    parser.add_argument("--integration-step-s", type=float, default=0.01)
    parser.add_argument("--report-step-s", type=float, default=0.02)
    parser.add_argument("--no-show", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    track = Track.from_json(args.track)
    engine = EngineModel.baja_br10()
    vehicle = VehicleModel(mass_kg=args.vehicle_mass_kg)
    tire = TireModel(
        wheel_radius_m=args.wheel_radius_in * INCH_TO_METRE,
        slip_stiffness_n_per_mps=args.tire_slip_stiffness,
    )
    cvt = IdealCVTModel(
        minimum_speed_ratio=args.minimum_cvt_ratio,
        maximum_speed_ratio=args.maximum_cvt_ratio,
        final_drive_ratio=args.final_drive_ratio,
    )
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
    bounded_case = StudyCase(
        name=f"{track.name} bounded perfect CVT",
        engine=engine,
        vehicle=vehicle,
        tire=tire,
        cvt=cvt,
        driver=driver,
        infinite_cvt=False,
    )
    reference_case = StudyCase(
        name=f"{track.name} infinite CVT reference",
        engine=engine,
        vehicle=vehicle,
        tire=tire,
        cvt=cvt,
        driver=driver,
        infinite_cvt=True,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Track: {track.name} ({track.length_m:.1f} m)")
    print(
        f"Bounded CVT: q={cvt.minimum_speed_ratio:.4f}–{cvt.maximum_speed_ratio:.4f}, "
        f"final drive={cvt.final_drive_ratio:.3f}, tire={args.wheel_radius_in:.2f} in"
    )
    print(
        f"Peak-power target: {engine.peak_power_rpm:.0f} rpm, "
        f"{engine.peak_power_w / 745.6998715822702:.3f} hp"
    )

    reference = run_simulation(case=reference_case, track=track, settings=settings)
    bounded = run_simulation(case=bounded_case, track=track, settings=settings)
    reference_summary = summarize_trace(reference, target_engine_rpm=engine.peak_power_rpm, ideal_peak_power_w=engine.peak_power_w)
    bounded_summary = compare_to_reference(
        summarize_trace(bounded, target_engine_rpm=engine.peak_power_rpm, ideal_peak_power_w=engine.peak_power_w),
        reference_summary,
    )

    bounded.write_csv(args.output_dir / "bounded_trace.csv")
    reference.write_csv(args.output_dir / "infinite_reference_trace.csv")
    (args.output_dir / "bounded_summary.json").write_text(
        json.dumps(bounded_summary, indent=2), encoding="utf-8"
    )
    (args.output_dir / "infinite_reference_summary.json").write_text(
        json.dumps(reference_summary, indent=2), encoding="utf-8"
    )
    (args.output_dir / "resolved_case.json").write_text(
        json.dumps(
            {
                "track": track.to_dict(),
                "engine": {
                    "target_rpm": engine.peak_power_rpm,
                    "peak_power_w": engine.peak_power_w,
                    "points": [asdict(point) for point in engine.points],
                },
                "vehicle": asdict(vehicle),
                "tire": asdict(tire),
                "cvt": asdict(cvt),
                "driver": asdict(driver),
                "settings": asdict(settings),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    plot_paths = plot_single_run(
        trace=bounded,
        reference=reference,
        track=track,
        target_engine_rpm=engine.peak_power_rpm,
        minimum_ratio=cvt.minimum_speed_ratio,
        maximum_ratio=cvt.maximum_speed_ratio,
        output_dir=args.output_dir,
        show=not args.no_show,
    )

    print("\nBounded result")
    print(f"  completed: {bounded_summary['completed']}")
    print(f"  lap time: {bounded_summary['lap_time_s']:.3f} s")
    print(f"  average speed: {bounded_summary['average_speed_kmh']:.2f} km/h")
    print(f"  maximum speed: {bounded_summary['maximum_speed_kmh']:.2f} km/h")
    print(f"  low / variable / high ratio time: "
          f"{bounded_summary['time_low_ratio_s']:.2f} / "
          f"{bounded_summary['time_variable_ratio_s']:.2f} / "
          f"{bounded_summary['time_high_ratio_s']:.2f} s")
    print(f"  outside target RPM band: {bounded_summary['time_outside_target_rpm_band_s']:.2f} s")
    print(
        "  average finite-ratio opportunity-loss power: "
        f"{bounded_summary['finite_ratio_opportunity_loss_average_power_hp']:.3f} hp"
    )
    print(
        "  average tire-slip loss power: "
        f"{bounded_summary['tire_slip_loss_average_power_hp']:.3f} hp"
    )
    print(
        "  average obstacle loss power: "
        f"{bounded_summary['obstacle_loss_average_power_hp']:.3f} hp"
    )
    print(f"  lap penalty vs infinite CVT: "
          f"{bounded_summary['lap_time_penalty_vs_infinite_s']:.3f} s "
          f"({bounded_summary['lap_time_penalty_vs_infinite_percent']:.2f}%)")
    print(f"\nWrote {len(plot_paths)} plots and CSV/JSON outputs to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
