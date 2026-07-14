from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


EVENT_PREDICTION_COLUMNS = (
    "case_id",
    "predicted_min_speed_kmh",
    "predicted_end_speed_kmh",
    "predicted_event_time_s",
    "predicted_recovery_distance_m",
)


def event_prediction_template(cases: pd.DataFrame) -> pd.DataFrame:
    template = cases[
        [
            "case_id",
            "analysis_group_id",
            "event_name",
            "entry_speed_kmh",
            "event_length_m",
        ]
    ].copy()
    for column in EVENT_PREDICTION_COLUMNS[1:]:
        template[column] = np.nan
    return template


def lap_prediction_template(track_profile: pd.DataFrame) -> pd.DataFrame:
    template = track_profile[["s_m"]].copy()
    template.insert(0, "scenario_id", "baseline")
    template["predicted_speed_kmh"] = np.nan
    return template


def compare_event_predictions(
    observed_cases: pd.DataFrame,
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing = [column for column in EVENT_PREDICTION_COLUMNS if column not in predictions.columns]
    if missing:
        raise ValueError(f"Event predictions are missing columns: {missing}")
    if predictions["case_id"].duplicated().any():
        duplicates = predictions.loc[predictions["case_id"].duplicated(keep=False), "case_id"].tolist()
        raise ValueError(f"Duplicate prediction case_id values: {duplicates[:10]}")
    merged = observed_cases.merge(
        predictions[list(EVENT_PREDICTION_COLUMNS)],
        on="case_id",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if (merged["_merge"] != "both").any():
        missing_cases = merged.loc[merged["_merge"] != "both", "case_id"].tolist()
        raise ValueError(f"Predictions are missing {len(missing_cases)} observed case IDs; first: {missing_cases[:5]}")
    merged = merged.drop(columns="_merge")
    numeric_predictions = list(EVENT_PREDICTION_COLUMNS[1:])
    for column in numeric_predictions:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    required_values = numeric_predictions[:3]
    if merged[required_values].isna().any().any():
        bad = merged.loc[merged[required_values].isna().any(axis=1), "case_id"].tolist()
        raise ValueError(f"Predictions contain blank/non-numeric required values; first case IDs: {bad[:5]}")

    mappings = {
        "min_speed_kmh": ("event_min_speed_kmh", "predicted_min_speed_kmh"),
        "end_speed_kmh": ("end_speed_kmh", "predicted_end_speed_kmh"),
        "event_time_s": ("event_time_s", "predicted_event_time_s"),
        "recovery_distance_m": ("recovery_distance_m", "predicted_recovery_distance_m"),
    }
    for label, (observed, predicted) in mappings.items():
        merged[f"{label}_error"] = merged[predicted] - merged[observed]
        merged[f"{label}_absolute_error"] = merged[f"{label}_error"].abs()
        denominator = merged[observed].abs().where(merged[observed].abs() > 1e-9)
        merged[f"{label}_absolute_percentage_error"] = merged[f"{label}_absolute_error"] / denominator

    entry_mps = merged["entry_speed_kmh"] / 3.6
    predicted_min_mps = merged["predicted_min_speed_kmh"] / 3.6
    predicted_end_mps = merged["predicted_end_speed_kmh"] / 3.6
    merged["predicted_specific_ke_change_to_min_j_per_kg"] = 0.5 * (entry_mps**2 - predicted_min_mps**2)
    merged["predicted_specific_ke_change_to_end_j_per_kg"] = 0.5 * (entry_mps**2 - predicted_end_mps**2)
    merged["specific_ke_to_min_error_j_per_kg"] = (
        merged["predicted_specific_ke_change_to_min_j_per_kg"]
        - merged["specific_ke_change_to_min_j_per_kg"]
    )
    merged["specific_ke_to_end_error_j_per_kg"] = (
        merged["predicted_specific_ke_change_to_end_j_per_kg"]
        - merged["specific_ke_change_to_end_j_per_kg"]
    )

    summary_rows = []
    summary_metrics = {
        "min_speed_kmh": "event_min_speed_kmh",
        "end_speed_kmh": "end_speed_kmh",
        "event_time_s": "event_time_s",
        "recovery_distance_m": "recovery_distance_m",
        "specific_ke_to_min_j_per_kg": "specific_ke_change_to_min_j_per_kg",
        "specific_ke_to_end_j_per_kg": "specific_ke_change_to_end_j_per_kg",
    }
    groups = [("ALL", merged), *list(merged.groupby("analysis_group_id", sort=False))]
    for group_id, group in groups:
        for metric, observed_column in summary_metrics.items():
            error_column = (
                f"{metric}_error"
                if f"{metric}_error" in group
                else metric.replace("_j_per_kg", "_error_j_per_kg")
            )
            if error_column not in group:
                continue
            pair = group[[observed_column, error_column]].dropna()
            if pair.empty:
                continue
            errors = pair[error_column]
            observed_iqr = float(pair[observed_column].quantile(0.75) - pair[observed_column].quantile(0.25))
            mae = float(errors.abs().mean())
            summary_rows.append(
                {
                    "analysis_group_id": group_id,
                    "metric": metric,
                    "matched_cases": int(len(pair)),
                    "bias": float(errors.mean()),
                    "mae": mae,
                    "rmse": float(np.sqrt(np.mean(errors**2))),
                    "median_absolute_error": float(errors.abs().median()),
                    "observed_iqr": observed_iqr,
                    "mae_divided_by_observed_iqr": mae / observed_iqr if observed_iqr > 1e-9 else math.nan,
                }
            )
    return merged, pd.DataFrame(summary_rows)


def compare_lap_profile(
    observed_profile: pd.DataFrame,
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_observed = {"s_m", "median_speed_kmh", "p25_speed_kmh", "p75_speed_kmh"}
    missing_observed = required_observed - set(observed_profile.columns)
    if missing_observed:
        raise ValueError(f"Observed profile is missing columns: {sorted(missing_observed)}")
    required_prediction = {"s_m", "predicted_speed_kmh"}
    missing_prediction = required_prediction - set(predictions.columns)
    if missing_prediction:
        raise ValueError(f"Predicted profile is missing columns: {sorted(missing_prediction)}")
    predicted = predictions.copy()
    if "scenario_id" not in predicted:
        predicted["scenario_id"] = "baseline"
    predicted["s_m"] = pd.to_numeric(predicted["s_m"], errors="coerce")
    predicted["predicted_speed_kmh"] = pd.to_numeric(predicted["predicted_speed_kmh"], errors="coerce")
    if predicted[["s_m", "predicted_speed_kmh"]].isna().any().any():
        raise ValueError("Predicted lap profile has blank or non-numeric s/speed values")

    observed = observed_profile.sort_values("s_m")
    x = observed["s_m"].to_numpy(float)
    rows = []
    summaries = []
    for scenario_id, scenario in predicted.groupby("scenario_id", sort=False):
        scenario = scenario.sort_values("s_m").copy()
        s = scenario["s_m"].to_numpy(float)
        for column in ("median_speed_kmh", "p25_speed_kmh", "p75_speed_kmh"):
            scenario[f"observed_{column}"] = np.interp(s, x, observed[column].to_numpy(float))
        scenario["speed_error_kmh"] = scenario["predicted_speed_kmh"] - scenario["observed_median_speed_kmh"]
        scenario["absolute_speed_error_kmh"] = scenario["speed_error_kmh"].abs()
        scenario["within_observed_iqr"] = scenario["predicted_speed_kmh"].between(
            scenario["observed_p25_speed_kmh"], scenario["observed_p75_speed_kmh"]
        )
        rows.append(scenario)
        error = scenario["speed_error_kmh"]
        summaries.append(
            {
                "scenario_id": scenario_id,
                "profile_points": int(len(scenario)),
                "speed_bias_kmh": float(error.mean()),
                "speed_mae_kmh": float(error.abs().mean()),
                "speed_rmse_kmh": float(np.sqrt(np.mean(error**2))),
                "fraction_within_observed_iqr": float(scenario["within_observed_iqr"].mean()),
            }
        )
    return pd.concat(rows, ignore_index=True), pd.DataFrame(summaries)


def compare_profile_event_entries(
    event_summary: pd.DataFrame,
    predicted_profile: pd.DataFrame,
) -> pd.DataFrame:
    if "scenario_id" not in predicted_profile:
        predicted_profile = predicted_profile.assign(scenario_id="baseline")
    rows = []
    for scenario_id, scenario in predicted_profile.groupby("scenario_id", sort=False):
        scenario = scenario.sort_values("s_m")
        for _, event in event_summary.iterrows():
            predicted_entry = float(
                np.interp(
                    float(event["event_start_s_m"]),
                    scenario["s_m"].to_numpy(float),
                    scenario["predicted_speed_kmh"].to_numpy(float),
                )
            )
            observed_entry = float(event["median_entry_speed_kmh"])
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "analysis_group_id": event["analysis_group_id"],
                    "event_name": event["event_name"],
                    "event_start_s_m": event["event_start_s_m"],
                    "observed_median_entry_speed_kmh": observed_entry,
                    "predicted_entry_speed_kmh": predicted_entry,
                    "entry_speed_error_kmh": predicted_entry - observed_entry,
                }
            )
    return pd.DataFrame(rows)

