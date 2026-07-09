#!/usr/bin/env python3
"""
Black-box API E2E tests for the CVT Simulator backend.

This is intentionally API-only: it does not import backend internals, does not touch
SQLite/Postgres directly, and validates the updated public black-box guide.

The required product acceptance path uses:

    POST /runs/from-library
    GET  /runs/{run_id}/input
    GET  /runs/{run_id}/preview
    GET  /runs/{run_id}/result
    POST /runs/{run_id}/rerun

The legacy/direct POST /runs endpoint is treated as an optional developer/debug
regression check only. It is not called unless --run-direct-regression is supplied.

Typical use from anywhere, while the backend is already running:

    python cvt_black_box_api_e2e.py --api http://localhost:8000/api/v1

For the most aggressive fresh-dev-DB check, including seeded tune/version mutation:

    python cvt_black_box_api_e2e.py --api http://localhost:8000/api/v1 --full-mutating --strict

Exit code:
    0 = all required checks passed
    1 = one or more required checks failed

No third-party packages are required.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import difflib
import json
import math
import os
import re
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib import error, parse, request

JSON = dict[str, Any] | list[Any] | str | int | float | bool | None

TERMINAL_SUCCESS_STATUSES = {
    "complete",
    "completed",
    "success",
    "succeeded",
    "done",
    "finished",
    "cached",
}
TERMINAL_FAILURE_STATUSES = {
    "failed",
    "error",
    "errored",
    "cancelled",
    "canceled",
    "invalid",
    "unsupported",
}
NON_TERMINAL_STATUSES = {
    "created",
    "queued",
    "pending",
    "running",
    "started",
    "submitted",
    "recomputing",
    "processing",
}

VOLATILE_COMPARE_KEYS = {
    "id",
    "run_id",
    "created_at",
    "updated_at",
    "submitted_at",
    "started_at",
    "finished_at",
    "completed_at",
    "duration_ms",
    "elapsed_ms",
    "cache_hit",
    "cache_status",
    "cache_entry_id",
    "artifact_id",
    "artifact_ref",
    "results_ref",
    "display_url",
    "url",
}

PREVIEW_EXPECTED_FIELD_PATTERNS = [
    "time_s",
    "primary_angular_speed",
    "secondary_angular_speed",
    "shift_position",
    "ratio",
    "speed",
    "distance",
]


class CheckFailure(AssertionError):
    pass


@dataclasses.dataclass
class HttpResponse:
    method: str
    path: str
    url: str
    status: int
    headers: dict[str, str]
    text: str
    json_data: Any
    artifact_path: str | None = None


@dataclasses.dataclass
class CheckRecord:
    name: str
    status: str
    detail: str = ""
    elapsed_s: float = 0.0


class BlackBoxHarness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.api = args.api.rstrip("/")
        self.account_id = args.account_id or f"bb-account-{uuid.uuid4().hex[:10]}"
        self.user_id = args.user_id or f"bb-user-{uuid.uuid4().hex[:10]}"
        self.run_tag = args.run_tag or f"bb-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.output_dir = Path(args.output_dir or f"black_box_api_artifacts/{self.run_tag}").resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[CheckRecord] = []
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.context: dict[str, Any] = {
            "api": self.api,
            "account_id": self.account_id,
            "user_id": self.user_id,
            "run_tag": self.run_tag,
            "output_dir": str(self.output_dir),
            "created_objects": {},
            "runs": {},
        }
        self._request_count = 0

    # ---------- user-visible logging ----------

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    def pass_msg(self, name: str, elapsed: float) -> None:
        self.log(f"PASS {name} ({elapsed:.2f}s)")

    def fail_msg(self, name: str, detail: str, elapsed: float) -> None:
        self.log(f"FAIL {name} ({elapsed:.2f}s)\n     {detail}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        self.log(f"WARN {msg}")

    # ---------- check orchestration ----------

    def check(self, name: str, fn: Callable[[], None]) -> None:
        start = time.monotonic()
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - this is a test harness
            elapsed = time.monotonic() - start
            detail = f"{type(exc).__name__}: {exc}"
            if self.args.verbose:
                detail += "\n" + traceback.format_exc()
            self.records.append(CheckRecord(name=name, status="FAIL", detail=detail, elapsed_s=elapsed))
            self.failures.append(f"{name}: {detail}")
            self.fail_msg(name, detail, elapsed)
            if self.args.stop_on_first_failure:
                self.finalize(exit_now=True)
        else:
            elapsed = time.monotonic() - start
            self.records.append(CheckRecord(name=name, status="PASS", elapsed_s=elapsed))
            self.pass_msg(name, elapsed)

    def assert_true(self, condition: bool, message: str) -> None:
        if not condition:
            raise CheckFailure(message)

    def soft_assert(self, condition: bool, message: str) -> None:
        if condition:
            return
        if self.args.strict:
            raise CheckFailure(message)
        self.warn(message)

    # ---------- HTTP ----------

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        headers: dict[str, str] | None = None,
        expected: Iterable[int] | range | None = range(200, 300),
        artifact_name: str | None = None,
    ) -> HttpResponse:
        method = method.upper()
        if path.startswith("http://") or path.startswith("https://"):
            url = path
            display_path = path
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = self.api + path
            display_path = path

        raw: bytes | None = None
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if body is not None:
            raw = json.dumps(body, sort_keys=True).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        req = request.Request(url, data=raw, headers=request_headers, method=method)
        status = 0
        response_headers: dict[str, str] = {}
        text = ""
        try:
            with request.urlopen(req, timeout=self.args.timeout) as resp:
                status = int(resp.status)
                response_headers = {k.lower(): v for k, v in resp.headers.items()}
                text = resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            status = int(exc.code)
            response_headers = {k.lower(): v for k, v in exc.headers.items()}
            text = exc.read().decode("utf-8", errors="replace")
        except error.URLError as exc:
            raise CheckFailure(f"could not connect to {url}: {exc}") from exc

        parsed_json: Any = None
        if text.strip():
            try:
                parsed_json = json.loads(text)
            except json.JSONDecodeError:
                parsed_json = None

        self._request_count += 1
        if artifact_name is None:
            safe_method = method.lower()
            safe_path = re.sub(r"[^a-zA-Z0-9_.-]+", "_", display_path.strip("/"))[:120] or "root"
            artifact_name = f"{self._request_count:03d}_{safe_method}_{safe_path}"
        artifact_path = self.output_dir / f"{artifact_name}.json"
        artifact = {
            "request": {
                "method": method,
                "url": url,
                "path": display_path,
                "headers": redact_headers(request_headers),
                "body": body,
            },
            "response": {
                "status": status,
                "headers": response_headers,
                "text": text if parsed_json is None else None,
                "json": parsed_json,
            },
        }
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True, default=str), encoding="utf-8")

        resp = HttpResponse(
            method=method,
            path=display_path,
            url=url,
            status=status,
            headers=response_headers,
            text=text,
            json_data=parsed_json,
            artifact_path=str(artifact_path),
        )

        if expected is not None and status not in expected:
            snippet = text.strip().replace("\n", " ")[:800]
            raise CheckFailure(
                f"{method} {display_path} returned HTTP {status}, expected {list(expected) if not isinstance(expected, range) else f'{expected.start}-{expected.stop - 1}'}. "
                f"Response: {snippet}. Saved: {artifact_path}"
            )
        return resp

    def optional_request(self, method: str, path: str, **kwargs: Any) -> HttpResponse | None:
        resp = self.request(method, path, expected=None, **kwargs)
        if 200 <= resp.status < 300:
            return resp
        if resp.status in {404, 405, 501}:
            self.warn(f"optional endpoint unavailable: {method} {path} returned HTTP {resp.status}")
            return None
        raise CheckFailure(f"optional endpoint {method} {path} returned unexpected HTTP {resp.status}: {resp.text[:500]}")

    # ---------- phases ----------

    def run_all(self) -> None:
        self.log(f"CVT black-box API E2E starting")
        self.log(f"API: {self.api}")
        self.log(f"Artifacts: {self.output_dir}")
        self.log(f"Account/user for created data: {self.account_id} / {self.user_id}")
        self.log("")

        self.check("phase 1: health endpoint", self.phase_health)
        self.check("phase 1: metadata endpoints", self.phase_metadata)
        self.check("phase 1: CORS PATCH preflight", self.phase_cors)
        self.check("phase 2: seeded institutions", self.phase_seeded_institutions)
        self.check("phase 2: public/default library objects", self.phase_seeded_public_objects)
        self.check("phase 3: engine draft/release/fork/deprecate/archive lifecycle", self.phase_engine_lifecycle)
        self.check("phase 4: CVT fork/release shape", self.phase_cvt_lifecycle)
        self.check("phase 4: output-system fork/release shape", self.phase_output_lifecycle)
        self.check("phase 4: vehicle assembly version pinning shape", self.phase_assembly_version_pinning)
        self.check("phase 5: tune/load-case/execution-preset selection", self.phase_tune_load_preset)

        if not self.args.skip_runs:
            self.check("phase 6: library-resolved run", self.phase_library_run)
            self.check("phase 7: stored run input/preview/result retrieval", self.phase_retrieve_run_data)
            self.check("phase 8: persisted rerun from frozen input", self.phase_persisted_rerun)
            if self.args.run_direct_regression and not self.args.skip_direct_compare:
                self.check("optional: direct debug endpoint regression comparison", self.phase_direct_comparison)
            else:
                self.warn("optional direct POST /runs regression skipped; pass --run-direct-regression to execute developer/debug comparison")
            if not self.args.skip_cache:
                self.check("phase 9: library-run cache reuse", self.phase_cache_reuse)
            self.check("phase 10: evictable full-result behavior surface", self.phase_eviction_surface)
            self.check("phase 11: stale/deprecated preservation behavior", self.phase_stale_deprecated_behavior)
        else:
            self.warn("run phases skipped by --skip-runs")

        self.check("final: generated acceptance checklist", self.phase_acceptance_report)
        self.finalize()

    def phase_health(self) -> None:
        resp = self.request("GET", "/health", artifact_name="health")
        self.assert_true(resp.status == 200, "health did not return HTTP 200")
        if isinstance(resp.json_data, dict):
            lower = json.dumps(resp.json_data).lower()
            self.assert_true("error" not in lower or "healthy" in lower, "health response looks error-like")

    def phase_metadata(self) -> None:
        for path in [
            "/metadata/conventions",
            "/metadata/catalog",
            "/metadata/editor-schema",
            "/metadata/simulation-case-schema",
        ]:
            resp = self.request("GET", path)
            self.assert_true(resp.status == 200, f"{path} did not return HTTP 200")
            if path.endswith("schema"):
                self.assert_true(isinstance(resp.json_data, dict), f"{path} did not return a JSON schema object")
            else:
                self.assert_true(is_json_object_or_array(resp.json_data), f"{path} did not return JSON object/array")
            lower = json.dumps(resp.json_data).lower()
            self.assert_true("database setup error" not in lower, f"{path} contains database setup error")

    def phase_cors(self) -> None:
        resp = self.request(
            "OPTIONS",
            "/library/engines/some-id/draft",
            headers={
                "Origin": self.args.origin,
                "Access-Control-Request-Method": "PATCH",
            },
            expected={200, 204},
            artifact_name="cors_patch_preflight",
        )
        methods = resp.headers.get("access-control-allow-methods", "")
        origin = resp.headers.get("access-control-allow-origin", "")
        self.assert_true(
            "PATCH" in methods.upper() or methods.strip() == "*" or origin,
            f"CORS response did not clearly allow PATCH. Headers: {resp.headers}",
        )

    def phase_seeded_institutions(self) -> None:
        resp = self.request("GET", "/library/institutions", artifact_name="institutions")
        items = as_list(resp.json_data)
        self.assert_true(items, "institutions list is empty")
        text = json.dumps(resp.json_data).lower()
        expected_groups = [
            ["mcmaster"],
            ["cornell"],
            ["virginia tech", "vt baja"],
            ["west virginia", "wvu"],
            ["rit", "rochester institute"],
        ]
        matched = [group for group in expected_groups if any(term in text for term in group)]
        self.assert_true(
            len(matched) >= 3,
            "expected at least three seeded Baja-oriented institutions among McMaster, Cornell, Virginia Tech, WVU, and RIT",
        )
        self.context["seeded_institution_matches"] = matched

    def phase_seeded_public_objects(self) -> None:
        resources = {
            "engines": "/library/engines?public_only=true",
            "cvt_designs": "/library/cvt-designs?public_only=true",
            "output_systems": "/library/output-systems?public_only=true",
            "vehicle_assemblies": "/library/vehicle-assemblies?public_only=true",
        }
        public: dict[str, Any] = {}
        for key, path in resources.items():
            resp = self.request("GET", path, artifact_name=f"public_{key}")
            items = as_list(resp.json_data)
            self.assert_true(items, f"{key} public/default list is empty")
            first = items[0]
            released_version_id = get_released_version_id(first)
            self.assert_true(released_version_id, f"first {key} item has no released_version_id: {first}")
            public[key] = {"items": items, "first": first, "released_version_id": released_version_id}

            # Normal public lists should not show archived objects.
            archived_flags = [is_truthy(find_first_value(item, "archived")) or is_truthy(find_first_value(item, "is_archived")) for item in items]
            self.assert_true(not any(archived_flags), f"{key} public_only list appears to include archived objects")

            meta_text = json.dumps(first).lower()
            self.soft_assert(
                any(term in meta_text for term in ["default", "catalog", "seed", "public"]),
                f"first {key} item did not visibly contain default/catalog/seed/public metadata; object was still listed and versioned",
            )
        self.context["public"] = public

    def phase_engine_lifecycle(self) -> None:
        body = {
            "account_id": self.account_id,
            "name": f"Black-box test engine {self.run_tag}",
            "description": "Temporary engine for API testing",
            "visibility": "private",
            "draft_payload": {
                "kind": "full_throttle_torque_curve",
                "equivalent_rotational_inertia_kg_m2": 0.1,
                "points": [
                    {"angular_speed_rad_per_s": 200.0, "torque_Nm": 24.0},
                    {"angular_speed_rad_per_s": 300.0, "torque_Nm": 23.0},
                ],
                "low_speed_braking_torque_Nm": -5.0,
                "low_speed_braking_peak_speed_rad_per_s": 50.0,
                "high_speed_braking_torque_Nm": -20.0,
                "high_speed_braking_transition_width_rad_per_s": 150.0,
            },
        }
        create = self.request("POST", "/library/engines", body=body, artifact_name="engine_create")
        engine = assert_json_dict(create.json_data, "engine create response")
        engine_id = require_id(engine, "created engine")
        self.context["created_objects"]["engine_id"] = engine_id
        self.assert_true(find_first_value(engine, "draft_payload") is not None, "created engine does not expose draft_payload")
        self.assert_true(not find_first_value(engine, "released_version_id"), "new engine unexpectedly has a released_version_id")

        original_name = find_first_value(engine, "name")
        patch = self.request(
            "PATCH",
            f"/library/engines/{engine_id}/draft",
            body={"description": None, "source_url": None},
            artifact_name="engine_patch_null_clear",
        )
        patched = assert_json_dict(patch.json_data, "patched engine response")
        self.assert_true(find_first_value(patched, "description") is None, "explicit description:null did not clear description")
        self.assert_true(find_first_value(patched, "draft_payload") is not None, "patch omitted draft_payload but draft payload was not preserved")
        if original_name is not None:
            self.assert_true(find_first_value(patched, "name") == original_name, "missing name field was not preserved across patch")

        release = self.request(
            "POST",
            f"/library/engines/{engine_id}/release",
            body={"release_notes": "black-box release"},
            artifact_name="engine_release",
        )
        version = assert_json_dict(release.json_data, "engine release response")
        engine_version_id = require_id(version, "engine version")
        self.context["created_objects"]["engine_version_id"] = engine_version_id
        self.assert_true(has_key(version, "validation_status") or has_key(version, "schema_version") or has_key(version, "payload_schema"), "engine version lacks visible validation/schema metadata")
        self.assert_true(has_key(version, "equivalent_rotational_inertia_kg_m2"), "engine version payload lacks equivalent_rotational_inertia_kg_m2")
        self.soft_assert("boundary" in json.dumps(version).lower(), "engine version payload does not visibly expose input-boundary metadata")

        # Check base engine released_version_id from list, because no single-object GET is guaranteed in the guide.
        all_engines = self.request("GET", "/library/engines?include_archived=true", artifact_name="engines_include_archived_after_release")
        found_engine = find_object_by_id(as_list(all_engines.json_data), engine_id)
        self.assert_true(found_engine is not None, "created engine not found in include_archived=true list after release")
        self.assert_true(
            get_released_version_id(found_engine) in {engine_version_id, None} or json_contains(found_engine, engine_version_id),
            "engine list item does not show released_version_id pointing at new version",
        )

        fork = self.request(
            "POST",
            f"/library/engines/versions/{engine_version_id}/fork",
            body={"account_id": self.account_id, "name": f"Forked black-box engine {self.run_tag}"},
            artifact_name="engine_fork",
        )
        forked_engine = assert_json_dict(fork.json_data, "forked engine response")
        forked_engine_id = require_id(forked_engine, "forked engine")
        self.context["created_objects"]["forked_engine_id"] = forked_engine_id
        provenance = find_first_value(forked_engine, "forked_from_version_id")
        if provenance is not None:
            self.assert_true(provenance == engine_version_id, f"forked_from_version_id {provenance!r} does not match {engine_version_id!r}")
        self.assert_true(find_first_value(forked_engine, "draft_payload") is not None, "forked engine lacks copied draft_payload")

        dep = self.request(
            "POST",
            f"/library/engines/versions/{engine_version_id}/deprecate",
            body={"validation_status": "deprecated", "message": "black-box stale version check"},
            artifact_name="engine_deprecate",
        )
        dep_text = json.dumps(dep.json_data).lower()
        self.assert_true("deprecated" in dep_text or "stale version" in dep_text, "deprecate response does not show deprecated/stale metadata")

        self.request("POST", f"/library/engines/{engine_id}/archive", artifact_name="engine_archive")
        normal = self.request("GET", "/library/engines", artifact_name="engines_normal_after_archive")
        archived = self.request("GET", "/library/engines?include_archived=true", artifact_name="engines_include_archived_after_archive")
        self.assert_true(not json_contains(normal.json_data, engine_id), "archived engine still appears in normal engine list")
        self.assert_true(json_contains(archived.json_data, engine_id), "archived engine missing from include_archived=true engine list")
        self.assert_true(json_contains(archived.json_data, engine_version_id), "archived engine/version historical identity missing from include_archived=true list")

    def phase_cvt_lifecycle(self) -> None:
        public = self.context.get("public") or {}
        seeded_version_id = ((public.get("cvt_designs") or {}).get("released_version_id"))
        if not seeded_version_id:
            cvts = as_list(self.request("GET", "/library/cvt-designs?public_only=true").json_data)
            seeded_version_id = get_released_version_id(cvts[0])
        self.assert_true(seeded_version_id, "no seeded CVT released version available")
        self.context["seeded_cvt_version_id"] = seeded_version_id

        fork = self.request(
            "POST",
            f"/library/cvt-designs/versions/{seeded_version_id}/fork",
            body={"account_id": self.account_id, "name": f"Forked black-box CVT {self.run_tag}"},
            artifact_name="cvt_fork",
        )
        forked_cvt = assert_json_dict(fork.json_data, "forked CVT response")
        forked_cvt_id = require_id(forked_cvt, "forked CVT")
        self.context["created_objects"]["forked_cvt_id"] = forked_cvt_id

        release = self.request(
            "POST",
            f"/library/cvt-designs/{forked_cvt_id}/release",
            body={"release_notes": "release forked CVT"},
            artifact_name="cvt_release",
        )
        cvt_version = assert_json_dict(release.json_data, "released CVT response")
        released_cvt_version_id = require_id(cvt_version, "released CVT version")
        self.context["created_objects"]["forked_cvt_version_id"] = released_cvt_version_id
        self.assert_true(has_key(cvt_version, "tuning_schema"), "released CVT version does not preserve tuning_schema")
        cvt_text = json.dumps(cvt_version).lower()
        self.assert_true("cinder_assembly" in cvt_text, "released CVT version does not visibly contain a CINDER assembly payload")
        payload = find_payload_like(cvt_version)
        nested_bad = False
        if isinstance(payload, dict) and isinstance(payload.get("cinder_assembly"), dict):
            nested_bad = "cinder_assembly" in payload["cinder_assembly"]
        self.assert_true(not nested_bad, "released CVT payload has cinder_assembly nested inside cinder_assembly")

        if not self.args.no_cleanup_created:
            self.optional_request("POST", f"/library/cvt-designs/{forked_cvt_id}/archive", artifact_name="cvt_archive_cleanup")

    def phase_output_lifecycle(self) -> None:
        public = self.context.get("public") or {}
        seeded_version_id = ((public.get("output_systems") or {}).get("released_version_id"))
        if not seeded_version_id:
            outputs = as_list(self.request("GET", "/library/output-systems?public_only=true").json_data)
            seeded_version_id = get_released_version_id(outputs[0])
        self.assert_true(seeded_version_id, "no seeded output-system released version available")
        self.context["seeded_output_version_id"] = seeded_version_id

        fork = self.request(
            "POST",
            f"/library/output-systems/versions/{seeded_version_id}/fork",
            body={"account_id": self.account_id, "name": f"Forked black-box output {self.run_tag}"},
            artifact_name="output_fork",
        )
        forked_output = assert_json_dict(fork.json_data, "forked output response")
        forked_output_id = require_id(forked_output, "forked output")
        self.context["created_objects"]["forked_output_id"] = forked_output_id

        release = self.request(
            "POST",
            f"/library/output-systems/{forked_output_id}/release",
            body={"release_notes": "release forked output"},
            artifact_name="output_release",
        )
        output_version = assert_json_dict(release.json_data, "released output response")
        released_output_version_id = require_id(output_version, "released output version")
        self.context["created_objects"]["forked_output_version_id"] = released_output_version_id
        self.assert_true(has_key(output_version, "direct_secondary_shaft_inertia_kg_m2"), "released output payload lacks direct_secondary_shaft_inertia_kg_m2")
        output_text = json.dumps(output_version).lower()
        self.soft_assert(any(term in output_text for term in ["gearbox", "final", "drivetrain"]), "released output payload does not visibly include gearbox/final-drive/drivetrain data")
        self.soft_assert("loss" in output_text, "released output payload does not visibly include loss-model data")

        if not self.args.no_cleanup_created:
            self.optional_request("POST", f"/library/output-systems/{forked_output_id}/archive", artifact_name="output_archive_cleanup")


    def phase_assembly_version_pinning(self) -> None:
        public = self.context.get("public") or {}
        assembly_info = public.get("vehicle_assemblies") or {}
        assembly_version_id = assembly_info.get("released_version_id")
        first_assembly = assembly_info.get("first")
        self.assert_true(assembly_version_id, "no seeded vehicle assembly released version available")
        self.context["seeded_assembly_version_id"] = assembly_version_id

        version_obj: Any = None
        detail = self.optional_request(
            "GET",
            f"/library/vehicle-assemblies/versions/{assembly_version_id}",
            artifact_name="vehicle_assembly_version_detail",
        )
        if detail is not None:
            version_obj = detail.json_data
        else:
            version_obj = first_assembly
            self.warn("vehicle assembly version detail endpoint unavailable; using list item for pinning shape checks")

        version_text = json.dumps(version_obj).lower()
        self.assert_true(json_contains(version_obj, assembly_version_id), "assembly version identity not visible in assembly version/list response")
        self.soft_assert("engine" in version_text and "version" in version_text, "assembly version does not visibly pin an engine version")
        self.soft_assert(("cvt" in version_text or "variator" in version_text) and "version" in version_text, "assembly version does not visibly pin a CVT version")
        self.soft_assert(("output" in version_text or "drivetrain" in version_text) and "version" in version_text, "assembly version does not visibly pin an output-system version")

        pinned_ids = find_all_key_values(version_obj, key_suffix="version_id")
        if detail is not None:
            self.assert_true(len(pinned_ids) >= 3, f"assembly version detail exposes fewer than three pinned *_version_id fields: {pinned_ids}")
        else:
            self.soft_assert(len(pinned_ids) >= 1, "assembly list item does not expose pinned version ids; detail endpoint was unavailable")

    def phase_tune_load_preset(self) -> None:
        endpoints = {
            "tunes": "/library/tunes",
            "load_cases": "/library/load-cases",
            "execution_presets": "/library/execution-presets",
        }
        for key, path in endpoints.items():
            resp = self.request("GET", path, artifact_name=key)
            items = as_list(resp.json_data)
            self.assert_true(items, f"{key} list is empty")
            item_id = require_id(items[0], f"first {key[:-1]}")
            self.context[f"seeded_{key[:-1]}_id"] = item_id

        if self.args.full_mutating or self.args.mutate_seeded_tune:
            tune_id = self.context["seeded_tune_id"]
            patched = self.request("PATCH", f"/library/tunes/{tune_id}", body={"notes": None}, artifact_name="tune_patch_null_clear")
            self.assert_true(find_first_value(patched.json_data, "notes") is None, "tune notes:null did not clear notes")
        else:
            self.warn("seeded tune null-clear patch skipped; pass --mutate-seeded-tune or --full-mutating to execute it")

    def phase_library_run(self) -> None:
        public = self.context.get("public") or {}
        assembly_version_id = ((public.get("vehicle_assemblies") or {}).get("released_version_id"))
        if not assembly_version_id:
            assemblies = as_list(self.request("GET", "/library/vehicle-assemblies?public_only=true").json_data)
            assembly_version_id = get_released_version_id(assemblies[0])
        tune_id = self.context.get("seeded_tune_id")
        load_case_id = self.context.get("seeded_load_case_id")
        execution_preset_id = self.context.get("seeded_execution_preset_id")
        self.assert_true(all([assembly_version_id, tune_id, load_case_id, execution_preset_id]), "missing seeded assembly/tune/load-case/execution preset id")
        self.context["assembly_version_id_for_run"] = assembly_version_id

        run_body = {
            "account_id": self.account_id,
            "created_by_user_id": self.user_id,
            "vehicle_assembly_version_id": assembly_version_id,
            "tune_id": tune_id,
            "load_case_id": load_case_id,
            "execution_preset_id": execution_preset_id,
        }
        self.context["library_run_body"] = run_body
        run_resp = self.request("POST", "/runs/from-library", body=run_body, artifact_name="library_run_submit")
        run_obj = assert_json_dict(run_resp.json_data, "library run response")
        run_id = require_id(run_obj, "library run")
        self.context["runs"]["library_run_id"] = run_id
        status = get_status(run_obj)
        if status:
            self.assert_true(status not in TERMINAL_FAILURE_STATUSES, f"library run failed immediately with status {status!r}")
        run_obj = self.wait_for_run_if_needed(run_id, run_obj, artifact_prefix="library_run_wait")
        status = get_status(run_obj)
        if status:
            self.assert_true(status in TERMINAL_SUCCESS_STATUSES or status not in TERMINAL_FAILURE_STATUSES, f"library run did not reach success status; latest status {status!r}")

        self.assert_true(has_key(run_obj, "contract_hash") or has_key(run_resp.json_data, "contract_hash"), "library run response/detail lacks contract_hash")
        self.context["runs"]["library_contract_hash"] = find_first_value(run_obj, "contract_hash") or find_first_value(run_resp.json_data, "contract_hash")
        self.soft_assert(has_key(run_obj, "cache_status") or has_key(run_obj, "cache_hit") or has_key(run_resp.json_data, "cache_status") or has_key(run_resp.json_data, "cache_hit"), "library run response/detail lacks visible cache status")
        self.soft_assert(any(k in json.dumps(run_obj).lower() for k in ["summary", "scalars", "stats"]), "library run response/detail lacks visible summary data")
        self.soft_assert("library" in json.dumps(run_obj).lower() or "library" in json.dumps(run_resp.json_data).lower(), "library run response does not visibly record source=library")

        runs_list = self.request("GET", "/runs", artifact_name="runs_list_after_library_run")
        self.assert_true(json_contains(runs_list.json_data, run_id), "library run ID is not present in persisted run history")

    def phase_retrieve_run_data(self) -> None:
        run_id = self.context["runs"].get("library_run_id")
        self.assert_true(run_id, "no library run id available")
        detail = self.request("GET", f"/runs/{run_id}", artifact_name="library_run_detail")
        input_resp = self.request("GET", f"/runs/{run_id}/input", artifact_name="library_run_input")
        preview_resp = self.request("GET", f"/runs/{run_id}/preview", artifact_name="library_run_preview")
        result_resp = self.request("GET", f"/runs/{run_id}/result", artifact_name="library_run_result")
        self.context["runs"]["library_detail"] = detail.json_data
        self.context["runs"]["library_input"] = input_resp.json_data
        self.context["runs"]["library_preview"] = preview_resp.json_data
        self.context["runs"]["library_result"] = result_resp.json_data
        self.context["runs"]["library_result_path"] = result_resp.artifact_path

        self.assert_true(is_json_object_or_array(input_resp.json_data), "/input did not return a JSON simulation case")
        self.assert_true(is_json_object_or_array(preview_resp.json_data), "/preview did not return JSON")
        self.assert_true(is_json_object_or_array(result_resp.json_data), "/result did not return JSON")

        detail_text = json.dumps(detail.json_data).lower()
        self.assert_true(any(term in detail_text for term in ["summary", "scalar", "stat", "peak", "final"]), "run detail lacks retrievable summary/stat data")

        preview_text = json.dumps(preview_resp.json_data).lower()
        missing_preview = [field for field in PREVIEW_EXPECTED_FIELD_PATTERNS if field.lower() not in preview_text]
        self.assert_true(not missing_preview, f"preview is missing expected field patterns: {missing_preview}")
        self.soft_assert(any(term in preview_text for term in ["version", "schema", "profile"]), "preview response does not visibly expose a preview/profile/schema version")

        preview_series = extract_timeseries(preview_resp.json_data)
        full_series = extract_timeseries(result_resp.json_data)
        self.assert_true(preview_series is not None, "could not find preview time-series points")
        self.assert_true(full_series is not None, "could not find full result time-series/report-table points")
        assert preview_series is not None and full_series is not None
        self.assert_true(len(preview_series.points) <= len(full_series.points), f"preview has more points ({len(preview_series.points)}) than full result ({len(full_series.points)})")
        self.assert_true(len(preview_series.points) >= 2, "preview has fewer than two points")
        self.assert_true(len(full_series.points) >= 2, "full result has fewer than two points")
        p0 = numeric_time(preview_series.points[0])
        p1 = numeric_time(preview_series.points[-1])
        f0 = numeric_time(full_series.points[0])
        f1 = numeric_time(full_series.points[-1])
        if None not in {p0, p1, f0, f1}:
            self.assert_true(close_float(p0, f0, abs_tol=self.args.float_tol, rel_tol=self.args.float_tol * 10), f"preview first time {p0} does not match full first time {f0}")
            self.assert_true(close_float(p1, f1, abs_tol=max(self.args.float_tol, 1e-4), rel_tol=self.args.float_tol * 100), f"preview last time {p1} does not match full last time {f1}")
        self.context["runs"]["library_preview_series_path"] = preview_series.path
        self.context["runs"]["library_full_series_path"] = full_series.path
        self.context["runs"]["library_preview_point_count"] = len(preview_series.points)
        self.context["runs"]["library_full_point_count"] = len(full_series.points)


    def phase_persisted_rerun(self) -> None:
        run_id = self.context["runs"].get("library_run_id")
        self.assert_true(run_id, "no original library run id available")
        original_input = self.context["runs"].get("library_input")
        original_preview = self.context["runs"].get("library_preview")
        original_result = self.context["runs"].get("library_result")
        self.assert_true(original_input is not None and original_preview is not None and original_result is not None, "original run input/preview/result must be retrieved before persisted rerun")

        rerun = self.request("POST", f"/runs/{run_id}/rerun", body={}, artifact_name="stored_rerun_submit")
        rerun_obj = assert_json_dict(rerun.json_data, "persisted rerun response")
        rerun_id = require_id(rerun_obj, "persisted rerun")
        self.context["runs"]["persisted_rerun_id"] = rerun_id
        rerun_obj = self.wait_for_run_if_needed(rerun_id, rerun_obj, artifact_prefix="stored_rerun_wait")
        status = get_status(rerun_obj)
        if status:
            self.assert_true(status in TERMINAL_SUCCESS_STATUSES or status not in TERMINAL_FAILURE_STATUSES, f"persisted rerun did not reach success status; latest status {status!r}")

        rerun_text = json.dumps(rerun_obj).lower() + json.dumps(rerun.json_data).lower()
        self.assert_true("library" in rerun_text, "persisted rerun response does not visibly report source = library")

        original_hash = self.context["runs"].get("library_contract_hash") or find_first_value(self.context["runs"].get("library_detail"), "contract_hash")
        rerun_hash = find_first_value(rerun_obj, "contract_hash") or find_first_value(rerun.json_data, "contract_hash")
        self.assert_true(original_hash and rerun_hash, "original/rerun contract_hash missing")
        self.assert_true(original_hash == rerun_hash, f"persisted rerun contract_hash {rerun_hash!r} differs from original {original_hash!r}")

        rerun_input = self.request("GET", f"/runs/{rerun_id}/input", artifact_name="stored_rerun_input")
        rerun_preview = self.request("GET", f"/runs/{rerun_id}/preview", artifact_name="stored_rerun_preview")
        rerun_result = self.request("GET", f"/runs/{rerun_id}/result", artifact_name="stored_rerun_result")
        self.context["runs"]["persisted_rerun_input"] = rerun_input.json_data
        self.context["runs"]["persisted_rerun_preview"] = rerun_preview.json_data
        self.context["runs"]["persisted_rerun_result"] = rerun_result.json_data

        input_cmp = compare_canonical_json(
            extract_frozen_input_snapshot(original_input),
            extract_frozen_input_snapshot(rerun_input.json_data),
            label_a="original_input_snapshot",
            label_b="rerun_input_snapshot",
        )
        input_cmp_path = self.output_dir / "original_vs_rerun_input_snapshot_comparison.json"
        input_cmp_path.write_text(json.dumps(dataclasses.asdict(input_cmp), indent=2, sort_keys=True, default=str), encoding="utf-8")
        if not input_cmp.ok:
            raise CheckFailure(f"persisted rerun frozen input differs from original: {input_cmp.summary}. Details saved to {input_cmp_path}")

        preview_cmp = compare_results(original_preview, rerun_preview.json_data, self.args.float_tol)
        preview_cmp_path = self.output_dir / "original_vs_rerun_preview_comparison.json"
        preview_cmp_path.write_text(json.dumps(dataclasses.asdict(preview_cmp), indent=2, sort_keys=True, default=str), encoding="utf-8")
        if not preview_cmp.ok:
            raise CheckFailure(f"persisted rerun preview differs from original: {preview_cmp.summary}. Details saved to {preview_cmp_path}")

        result_cmp = compare_results(original_result, rerun_result.json_data, self.args.float_tol)
        result_cmp_path = self.output_dir / "original_vs_rerun_result_comparison.json"
        result_cmp_path.write_text(json.dumps(dataclasses.asdict(result_cmp), indent=2, sort_keys=True, default=str), encoding="utf-8")
        if not result_cmp.ok:
            raise CheckFailure(f"persisted rerun result differs from original: {result_cmp.summary}. Details saved to {result_cmp_path}")

        runs_list = self.request("GET", "/runs", artifact_name="runs_list_after_persisted_rerun")
        self.assert_true(json_contains(runs_list.json_data, rerun_id), "persisted rerun ID is not present in persisted run history")
        self.context["runs"]["persisted_rerun_result_compare"] = dataclasses.asdict(result_cmp)

    def phase_direct_comparison(self) -> None:
        frozen_input = self.context["runs"].get("library_input")
        self.assert_true(frozen_input is not None, "no frozen input available from library run")
        direct = self.request("POST", self.args.direct_regression_endpoint, body=frozen_input, artifact_name="direct_debug_run_submit")
        direct_obj = assert_json_dict(direct.json_data, "direct run response")
        direct_run_id = require_id(direct_obj, "direct run")
        self.context["runs"]["direct_run_id"] = direct_run_id
        direct_obj = self.wait_for_run_if_needed(direct_run_id, direct_obj, artifact_prefix="direct_run_wait")
        status = get_status(direct_obj)
        if status:
            self.assert_true(status in TERMINAL_SUCCESS_STATUSES or status not in TERMINAL_FAILURE_STATUSES, f"direct run did not reach success status; latest status {status!r}")
        direct_result = self.request("GET", f"/runs/{direct_run_id}/result", artifact_name="direct_run_result")
        self.context["runs"]["direct_result"] = direct_result.json_data
        self.context["runs"]["direct_result_path"] = direct_result.artifact_path

        library_result = self.context["runs"].get("library_result")
        self.assert_true(library_result is not None, "no library result available")
        comparison = compare_results(library_result, direct_result.json_data, self.args.float_tol)
        diff_path = self.output_dir / "library_vs_direct_debug_comparison.json"
        diff_path.write_text(json.dumps(dataclasses.asdict(comparison), indent=2, sort_keys=True, default=str), encoding="utf-8")
        if not comparison.ok:
            raise CheckFailure(f"library result and optional direct debug result differ: {comparison.summary}. Details saved to {diff_path}")
        self.context["runs"]["library_direct_debug_compare"] = dataclasses.asdict(comparison)

    def phase_cache_reuse(self) -> None:
        run_body = self.context.get("library_run_body")
        self.assert_true(run_body, "no library run body saved")
        original_detail = self.context["runs"].get("library_detail") or self.context["runs"].get("library_result") or {}
        original_hash = find_first_value(original_detail, "contract_hash")
        if original_hash is None:
            original_hash = find_first_value(self.context["runs"].get("library_result"), "contract_hash")

        cached = self.request("POST", "/runs/from-library", body=run_body, artifact_name="library_run_cached_submit")
        cached_obj = assert_json_dict(cached.json_data, "cached library run response")
        cached_run_id = require_id(cached_obj, "cached/repeated library run")
        self.context["runs"]["cached_library_run_id"] = cached_run_id
        cached_obj = self.wait_for_run_if_needed(cached_run_id, cached_obj, artifact_prefix="cached_library_run_wait")
        cached_hash = find_first_value(cached_obj, "contract_hash") or find_first_value(cached.json_data, "contract_hash")
        if original_hash is not None and cached_hash is not None:
            self.assert_true(original_hash == cached_hash, f"cached run contract_hash {cached_hash!r} differs from first run {original_hash!r}")
        else:
            self.warn("could not compare contract_hash because one response lacked it")

        original_cache_entry = find_first_value(original_detail, "cache_entry_id") or find_first_value(self.context["runs"].get("library_detail"), "cache_entry_id")
        cached_cache_entry = find_first_value(cached_obj, "cache_entry_id")
        if original_cache_entry and cached_cache_entry:
            self.assert_true(str(original_cache_entry) == str(cached_cache_entry), f"cached run cache_entry_id {cached_cache_entry!r} differs from original {original_cache_entry!r}")

        cache_hit = find_first_value(cached_obj, "cache_hit")
        cache_status = str(find_first_value(cached_obj, "cache_status") or "").lower()
        cache_text = json.dumps(cached_obj).lower()
        self.soft_assert(
            cache_hit is True or "hit" in cache_status or "cache hit" in cache_text or "cached" in cache_status,
            "repeated library run did not visibly report a cache hit/cache reuse",
        )
        self.request("GET", f"/runs/{cached_run_id}/preview", artifact_name="cached_library_run_preview")
        self.request("GET", f"/runs/{cached_run_id}/result", artifact_name="cached_library_run_result")

    def phase_eviction_surface(self) -> None:
        run_id = self.context["runs"].get("library_run_id")
        frozen_input = self.context["runs"].get("library_input")
        self.assert_true(run_id and frozen_input is not None, "need library run and frozen input for eviction-surface checks")

        # The guide says V1 has no public admin eviction endpoint. If a debug endpoint exists later,
        # the template allows exercising it without changing this script.
        if self.args.eviction_endpoint_template:
            endpoint = self.args.eviction_endpoint_template.format(run_id=run_id)
            evict_resp = self.request("POST", endpoint, artifact_name="debug_evict_full_result")
            self.assert_true(200 <= evict_resp.status < 300, "eviction endpoint did not succeed")
            self.request("GET", f"/runs/{run_id}/input", artifact_name="post_evict_input_survives")
            self.request("GET", f"/runs/{run_id}/preview", artifact_name="post_evict_preview_survives")
            detail = self.request("GET", f"/runs/{run_id}", artifact_name="post_evict_detail_survives")
            self.assert_true(any(term in json.dumps(detail.json_data).lower() for term in ["summary", "scalar", "stat"]), "summary data unavailable after eviction")
        else:
            self.warn("full-result eviction not executed because V1 has no public admin eviction endpoint; use --eviction-endpoint-template if you add one")

        # Product-visible regeneration path: rerun the persisted run from its frozen stored input.
        rerun = self.request("POST", f"/runs/{run_id}/rerun", body={}, artifact_name="eviction_surface_persisted_rerun")
        rerun_obj = assert_json_dict(rerun.json_data, "eviction-surface persisted rerun response")
        rerun_id = require_id(rerun_obj, "eviction-surface persisted rerun")
        self.context["runs"]["eviction_surface_persisted_rerun_id"] = rerun_id
        rerun_obj = self.wait_for_run_if_needed(rerun_id, rerun_obj, artifact_prefix="eviction_surface_persisted_rerun_wait")
        status = get_status(rerun_obj)
        if status:
            self.assert_true(status not in TERMINAL_FAILURE_STATUSES, f"eviction-surface persisted rerun failed with status {status!r}")
        self.request("GET", f"/runs/{rerun_id}/input", artifact_name="eviction_surface_persisted_rerun_input")
        self.request("GET", f"/runs/{rerun_id}/preview", artifact_name="eviction_surface_persisted_rerun_preview")
        self.request("GET", f"/runs/{rerun_id}/result", artifact_name="eviction_surface_persisted_rerun_result")

    def phase_stale_deprecated_behavior(self) -> None:
        run_id = self.context["runs"].get("library_run_id")
        self.assert_true(run_id, "no historical run available for stale/deprecated preservation check")
        # Always verify old runs remain retrievable after our earlier deprecation/archive operations.
        self.request("GET", f"/runs/{run_id}", artifact_name="historical_run_detail_after_deprecate_archive")
        self.request("GET", f"/runs/{run_id}/input", artifact_name="historical_run_input_after_deprecate_archive")
        self.request("GET", f"/runs/{run_id}/preview", artifact_name="historical_run_preview_after_deprecate_archive")

        if self.args.full_mutating or self.args.mutate_seeded_versions:
            self.warn("attempting seeded pinned-version deprecation because --mutate-seeded-versions/--full-mutating was set")
            frozen_input = self.context["runs"].get("library_input")
            pinned = find_likely_pinned_version_id(frozen_input, preferred_terms=["engine"])
            self.assert_true(pinned, "could not locate a pinned engine version id in frozen input for seeded deprecation test")
            dep = self.optional_request(
                "POST",
                f"/library/engines/versions/{pinned}/deprecate",
                body={"validation_status": "deprecated", "message": f"black-box pinned seeded deprecation {self.run_tag}"},
                artifact_name="seeded_pinned_engine_deprecate",
            )
            self.assert_true(dep is not None, "seeded pinned deprecation endpoint unavailable")
            rerun = self.request("POST", "/runs/from-library", body=self.context["library_run_body"], artifact_name="run_after_seeded_deprecate")
            rerun_obj = assert_json_dict(rerun.json_data, "run after seeded deprecate response")
            txt = json.dumps(rerun_obj).lower()
            self.soft_assert(any(term in txt for term in ["deprecated", "needs_migration", "warning", "warn"]), "run after deprecated pinned version did not visibly expose a resolver warning")
        else:
            self.warn("seeded pinned-version deprecation skipped; pass --mutate-seeded-versions or --full-mutating on a fresh dev DB to test resolver warnings")

    def phase_acceptance_report(self) -> None:
        checklist = [
            ("health and metadata endpoints return 200", self.record_passed("phase 1: health endpoint") and self.record_passed("phase 1: metadata endpoints")),
            ("CORS permits PATCH preflight", self.record_passed("phase 1: CORS PATCH preflight")),
            ("institutions seed correctly", self.record_passed("phase 2: seeded institutions")),
            ("public/default engines, CVTs, output systems, and assemblies list correctly", self.record_passed("phase 2: public/default library objects")),
            ("draft update respects explicit null vs missing field", self.record_passed("phase 3: engine draft/release/fork/deprecate/archive lifecycle")),
            ("release creates immutable version", self.record_passed("phase 3: engine draft/release/fork/deprecate/archive lifecycle")),
            ("fork copies source payload and provenance", self.record_passed("phase 3: engine draft/release/fork/deprecate/archive lifecycle")),
            ("CVT fork/release preserves cinder_assembly and tuning_schema shape", self.record_passed("phase 4: CVT fork/release shape")),
            ("output system owns gearbox/final-drive/direct secondary-shaft inertia", self.record_passed("phase 4: output-system fork/release shape")),
            ("vehicle assembly versions pin released engine, CVT, and output-system versions", self.record_passed("phase 4: vehicle assembly version pinning shape")),
            ("archive hides object from normal lists but include_archived reveals it", self.record_passed("phase 3: engine draft/release/fork/deprecate/archive lifecycle")),
            ("deprecate/supersede metadata is visible and does not mutate old runs", self.record_passed("phase 3: engine draft/release/fork/deprecate/archive lifecycle") and (self.record_passed("phase 11: stale/deprecated preservation behavior") or self.args.skip_runs)),
            ("library run resolves and completes", self.record_passed("phase 6: library-resolved run") or self.args.skip_runs),
            ("frozen input is retrievable", self.record_passed("phase 7: stored run input/preview/result retrieval") or self.args.skip_runs),
            ("full result is retrievable while artifact exists", self.record_passed("phase 7: stored run input/preview/result retrieval") or self.args.skip_runs),
            ("preview is retrievable and downsampled/profile-versioned", self.record_passed("phase 7: stored run input/preview/result retrieval") or self.args.skip_runs),
            ("summary stats are retrievable from run detail", self.record_passed("phase 7: stored run input/preview/result retrieval") or self.args.skip_runs),
            ("persisted rerun from frozen input matches original library run output", self.record_passed("phase 8: persisted rerun from frozen input") or self.args.skip_runs),
            ("repeated library run reuses cache", self.record_passed("phase 9: library-run cache reuse") or self.args.skip_runs or self.args.skip_cache),
            ("old input + preview survive full-result eviction behavior", self.record_passed("phase 10: evictable full-result behavior surface") or self.args.skip_runs),
            ("POST /runs/{run_id}/rerun can regenerate full output", self.record_passed("phase 10: evictable full-result behavior surface") or self.args.skip_runs),
            ("direct POST /runs comparison, if enabled, is treated as optional/dev-only", (not self.args.run_direct_regression) or self.record_passed("optional: direct debug endpoint regression comparison")),
        ]
        report_lines = [
            "# CVT Simulator black-box API test report",
            "",
            f"- API: `{self.api}`",
            f"- Run tag: `{self.run_tag}`",
            f"- Account: `{self.account_id}`",
            f"- User: `{self.user_id}`",
            f"- Generated: `{_dt.datetime.now().isoformat(timespec='seconds')}`",
            "",
            "## Acceptance checklist",
            "",
        ]
        for label, ok in checklist:
            report_lines.append(f"- [{'x' if ok else ' '}] {label}")
        report_lines.extend(["", "## Check records", ""])
        for rec in self.records:
            report_lines.append(f"- **{rec.status}** `{rec.name}` ({rec.elapsed_s:.2f}s){': ' + rec.detail if rec.detail else ''}")
        if self.warnings:
            report_lines.extend(["", "## Warnings", ""])
            for warning in self.warnings:
                report_lines.append(f"- {warning}")
        if self.failures:
            report_lines.extend(["", "## Failures", ""])
            for failure in self.failures:
                report_lines.append(f"- {failure}")
        report = "\n".join(report_lines) + "\n"
        report_path = self.output_dir / "REPORT.md"
        report_path.write_text(report, encoding="utf-8")
        self.context["report_path"] = str(report_path)
        self.assert_true(report_path.exists(), "report was not written")

    def record_passed(self, name: str) -> bool:
        return any(rec.name == name and rec.status == "PASS" for rec in self.records)

    def wait_for_run_if_needed(self, run_id: str, run_obj: dict[str, Any], *, artifact_prefix: str) -> dict[str, Any]:
        status = get_status(run_obj)
        if not status or status in TERMINAL_SUCCESS_STATUSES:
            return run_obj
        if status in TERMINAL_FAILURE_STATUSES:
            raise CheckFailure(f"run {run_id} is in failure status {status!r}")
        if status not in NON_TERMINAL_STATUSES:
            # Unknown status; do one detail fetch, but do not wait forever.
            detail = self.request("GET", f"/runs/{run_id}", artifact_name=f"{artifact_prefix}_detail_unknown_status")
            if isinstance(detail.json_data, dict):
                run_obj = detail.json_data
                status = get_status(run_obj)
                if not status or status in TERMINAL_SUCCESS_STATUSES:
                    return run_obj

        deadline = time.monotonic() + self.args.run_wait_seconds
        attempt = 0
        latest = run_obj
        while time.monotonic() < deadline:
            attempt += 1
            time.sleep(self.args.run_poll_interval_seconds)
            detail = self.request("GET", f"/runs/{run_id}", artifact_name=f"{artifact_prefix}_{attempt:02d}")
            if isinstance(detail.json_data, dict):
                latest = detail.json_data
            status = get_status(latest)
            if not status or status in TERMINAL_SUCCESS_STATUSES:
                return latest
            if status in TERMINAL_FAILURE_STATUSES:
                raise CheckFailure(f"run {run_id} entered failure status {status!r}")
        raise CheckFailure(f"run {run_id} did not complete within {self.args.run_wait_seconds}s; latest status={get_status(latest)!r}")

    def finalize(self, *, exit_now: bool = False) -> None:
        summary = {
            "api": self.api,
            "run_tag": self.run_tag,
            "account_id": self.account_id,
            "user_id": self.user_id,
            "output_dir": str(self.output_dir),
            "passed": sum(1 for r in self.records if r.status == "PASS"),
            "failed": sum(1 for r in self.records if r.status == "FAIL"),
            "warnings": len(self.warnings),
            "records": [dataclasses.asdict(r) for r in self.records],
            "warning_messages": self.warnings,
            "failure_messages": self.failures,
            "context": self.context,
        }
        summary_path = self.output_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
        self.log("")
        self.log(f"Summary written to: {summary_path}")
        report = self.context.get("report_path")
        if report:
            self.log(f"Markdown report: {report}")
        self.log(f"PASS={summary['passed']} FAIL={summary['failed']} WARN={summary['warnings']}")
        if self.failures:
            self.log("\nFailures:")
            for failure in self.failures:
                self.log(f"- {failure}")
        if exit_now:
            sys.exit(1 if self.failures else 0)
        if self.failures:
            sys.exit(1)
        sys.exit(0)


# ---------- JSON helpers ----------


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = dict(headers)
    for key in list(redacted):
        if key.lower() in {"authorization", "cookie", "set-cookie"}:
            redacted[key] = "<redacted>"
    return redacted


def is_json_object_or_array(value: Any) -> bool:
    return isinstance(value, (dict, list))


def assert_json_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CheckFailure(f"{label} is not a JSON object: {type(value).__name__}")
    return value


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ["items", "data", "results", "objects", "rows"]:
            if isinstance(value.get(key), list):
                return value[key]
    raise CheckFailure(f"expected list or list wrapper, got {type(value).__name__}: {str(value)[:300]}")


def require_id(value: Any, label: str) -> str:
    if isinstance(value, dict):
        item_id = value.get("id")
        if item_id is not None:
            return str(item_id)
    raise CheckFailure(f"{label} lacks top-level id: {value}")


def get_released_version_id(value: Any) -> str | None:
    direct = find_first_value(value, "released_version_id")
    return str(direct) if direct else None


def find_first_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_first_value(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first_value(child, key)
            if found is not None:
                return found
    return None


def has_key(value: Any, key: str) -> bool:
    sentinel = object()
    return find_first_value_or(value, key, sentinel) is not sentinel


def find_first_value_or(value: Any, key: str, default: Any) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_first_value_or(child, key, default)
            if found is not default:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first_value_or(child, key, default)
            if found is not default:
                return found
    return default


def json_contains(value: Any, needle: str) -> bool:
    return str(needle) in json.dumps(value, sort_keys=True, default=str)


def find_object_by_id(items: list[Any], object_id: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and str(item.get("id")) == str(object_id):
            return item
    return None


def is_truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "archived"}
    return bool(value)


def find_payload_like(obj: Any) -> Any:
    if isinstance(obj, dict):
        for key in ["payload", "version_payload", "released_payload", "draft_payload", "cinder_assembly"]:
            if key in obj:
                return obj[key]
        # If no canonical payload key exists, the object itself may be the payload wrapper.
        return obj
    return obj


def get_status(obj: Any) -> str | None:
    status = find_first_value(obj, "status") or find_first_value(obj, "run_status") or find_first_value(obj, "results_status")
    if status is None:
        return None
    return str(status).strip().lower()


def find_all_key_values(obj: Any, *, key_suffix: str | None = None, key_name: str | None = None) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                child_path = f"{path}.{k}" if path else k
                if (key_name is not None and k == key_name) or (key_suffix is not None and k.endswith(key_suffix)):
                    found.append((child_path, v))
                walk(v, child_path)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")

    walk(obj, "")
    return found


def find_likely_pinned_version_id(obj: Any, preferred_terms: list[str]) -> str | None:
    candidates: list[tuple[int, str, Any]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                child_path = f"{path}.{k}" if path else k
                if isinstance(v, (str, int)) and k.endswith("version_id"):
                    score = sum(10 for term in preferred_terms if term.lower() in child_path.lower())
                    score += 1
                    candidates.append((score, child_path, str(v)))
                walk(v, child_path)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")

    walk(obj, "")
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return str(candidates[0][2])


# ---------- timeseries and comparison ----------


@dataclasses.dataclass
class TimeSeriesCandidate:
    path: str
    points: list[dict[str, Any]]


@dataclasses.dataclass
class ResultComparison:
    ok: bool
    summary: str
    method: str
    compared_points: int = 0
    compared_values: int = 0
    max_abs_diff: float = 0.0
    max_diff_path: str = ""
    warnings: list[str] = dataclasses.field(default_factory=list)
    text_diff: list[str] = dataclasses.field(default_factory=list)


def extract_timeseries(obj: Any) -> TimeSeriesCandidate | None:
    candidates: list[TimeSeriesCandidate] = []

    def is_point_dict(x: Any) -> bool:
        return isinstance(x, dict) and any(k in x for k in ["time_s", "time", "t"]) and len(x) >= 2

    def score(candidate: TimeSeriesCandidate) -> tuple[int, int, int]:
        keys_text = json.dumps(candidate.points[: min(len(candidate.points), 3)]).lower()
        expected_hits = sum(1 for p in PREVIEW_EXPECTED_FIELD_PATTERNS if p.lower() in keys_text)
        return (len(candidate.points), expected_hits, len(keys_text))

    def walk(value: Any, path: str) -> None:
        if isinstance(value, list):
            if len(value) >= 2 and all(is_point_dict(x) for x in value[: min(5, len(value))]):
                dict_points = [x for x in value if isinstance(x, dict)]
                candidates.append(TimeSeriesCandidate(path=path, points=dict_points))
            for i, child in enumerate(value[:20]):
                walk(child, f"{path}[{i}]")
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{path}.{k}" if path else k)

    walk(obj, "")
    if not candidates:
        return None
    candidates.sort(key=score, reverse=True)
    return candidates[0]


def numeric_time(point: dict[str, Any]) -> float | None:
    for key in ["time_s", "time", "t"]:
        value = point.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def close_float(a: float, b: float, *, abs_tol: float, rel_tol: float) -> bool:
    return math.isclose(float(a), float(b), abs_tol=abs_tol, rel_tol=rel_tol)


def flatten_numeric_leaves(obj: Any, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and math.isfinite(float(v)):
                out[path] = float(v)
            elif isinstance(v, (dict, list)):
                out.update(flatten_numeric_leaves(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{prefix}[{i}]"
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and math.isfinite(float(v)):
                out[path] = float(v)
            elif isinstance(v, (dict, list)):
                out.update(flatten_numeric_leaves(v, path))
    return out


def extract_frozen_input_snapshot(obj: Any) -> Any:
    """Return the stable frozen simulation input snapshot from a run input response.

    The API guide describes /input as the frozen full CINDER case and also names
    input_document_snapshot. Different backend revisions may wrap it, so this
    helper accepts either shape without weakening the equality check.
    """
    if isinstance(obj, dict):
        for key in [
            "input_document_snapshot",
            "input_contract",
            "frozen_input",
            "simulation_case",
            "case",
        ]:
            if key in obj:
                return obj[key]
    return obj


def compare_canonical_json(a: Any, b: Any, *, label_a: str, label_b: str) -> ResultComparison:
    a_text = json.dumps(strip_volatile(a), sort_keys=True, indent=2, default=str)
    b_text = json.dumps(strip_volatile(b), sort_keys=True, indent=2, default=str)
    if a_text == b_text:
        return ResultComparison(ok=True, summary="canonical JSON matched", method="canonical_json")
    diff = list(difflib.unified_diff(a_text.splitlines(), b_text.splitlines(), fromfile=label_a, tofile=label_b, lineterm=""))[:400]
    return ResultComparison(ok=False, summary="canonical JSON differs", method="canonical_json", text_diff=diff)


def compare_results(library_result: Any, direct_result: Any, tol: float) -> ResultComparison:
    lib_series = extract_timeseries(library_result)
    dir_series = extract_timeseries(direct_result)
    warnings: list[str] = []
    if lib_series and dir_series:
        if len(lib_series.points) != len(dir_series.points):
            return ResultComparison(
                ok=False,
                summary=f"timeseries lengths differ: library={len(lib_series.points)} direct={len(dir_series.points)}; paths {lib_series.path!r} vs {dir_series.path!r}",
                method="timeseries",
                compared_points=min(len(lib_series.points), len(dir_series.points)),
                warnings=warnings,
            )
        max_diff = 0.0
        max_path = ""
        compared_values = 0
        # Compare every point for the intersection of numeric leaf paths inside that point.
        for i, (lp, dp) in enumerate(zip(lib_series.points, dir_series.points, strict=True)):
            lnums = flatten_numeric_leaves(lp)
            dnums = flatten_numeric_leaves(dp)
            common = sorted(set(lnums).intersection(dnums))
            if not common:
                warnings.append(f"no common numeric leaves at point {i}")
                continue
            for path in common:
                compared_values += 1
                diff = abs(lnums[path] - dnums[path])
                if diff > max_diff:
                    max_diff = diff
                    max_path = f"point[{i}].{path}: {lnums[path]} vs {dnums[path]}"
                if not close_float(lnums[path], dnums[path], abs_tol=tol, rel_tol=tol * 10):
                    return ResultComparison(
                        ok=False,
                        summary=f"numeric mismatch at {max_path}; abs diff={max_diff:g}, tol={tol:g}",
                        method="timeseries",
                        compared_points=i + 1,
                        compared_values=compared_values,
                        max_abs_diff=max_diff,
                        max_diff_path=max_path,
                        warnings=warnings,
                    )
        return ResultComparison(
            ok=True,
            summary=f"timeseries matched: {len(lib_series.points)} points, {compared_values} numeric values, max abs diff={max_diff:g}",
            method="timeseries",
            compared_points=len(lib_series.points),
            compared_values=compared_values,
            max_abs_diff=max_diff,
            max_diff_path=max_path,
            warnings=warnings,
        )

    # Fallback: canonical JSON diff after dropping obvious wrapper metadata.
    lib_clean = strip_volatile(library_result)
    dir_clean = strip_volatile(direct_result)
    lib_text = json.dumps(lib_clean, sort_keys=True, indent=2, default=str)
    dir_text = json.dumps(dir_clean, sort_keys=True, indent=2, default=str)
    if lib_text == dir_text:
        return ResultComparison(ok=True, summary="canonical JSON matched", method="canonical_json")
    diff = list(difflib.unified_diff(lib_text.splitlines(), dir_text.splitlines(), fromfile="library", tofile="direct", lineterm=""))[:400]
    return ResultComparison(ok=False, summary="canonical JSON differs and no comparable timeseries was found", method="canonical_json", text_diff=diff)


def strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE_COMPARE_KEYS}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    if isinstance(value, float):
        return round(value, 12)
    return value


# ---------- CLI ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run black-box API E2E tests against a running CVT Simulator backend.")
    parser.add_argument("--api", default="http://localhost:8000/api/v1", help="API root, default: http://localhost:8000/api/v1")
    parser.add_argument("--origin", default="http://localhost:5173", help="Origin header used for CORS preflight")
    parser.add_argument("--account-id", default=None, help="Account id to place in created test objects; default is unique")
    parser.add_argument("--user-id", default=None, help="User id to place in created test runs; default is unique")
    parser.add_argument("--run-tag", default=None, help="Human-readable tag used in created object names and artifact folder")
    parser.add_argument("--output-dir", default=None, help="Directory for JSON artifacts and markdown report")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout per request in seconds")
    parser.add_argument("--run-wait-seconds", type=float, default=180.0, help="Max time to wait for async run completion")
    parser.add_argument("--run-poll-interval-seconds", type=float, default=2.0, help="Polling interval for async run status")
    parser.add_argument("--float-tol", type=float, default=1e-8, help="Absolute float tolerance for library vs direct comparisons")
    parser.add_argument("--strict", action="store_true", help="Promote soft warnings to failures")
    parser.add_argument("--verbose", action="store_true", help="Show tracebacks on failures")
    parser.add_argument("--stop-on-first-failure", action="store_true", help="Stop immediately on the first failed check")
    parser.add_argument("--skip-runs", action="store_true", help="Skip run submission/retrieval/comparison phases")
    parser.add_argument("--skip-direct-compare", action="store_true", help="Deprecated compatibility flag. Direct POST /runs is not part of product acceptance and is skipped unless --run-direct-regression is supplied.")
    parser.add_argument("--run-direct-regression", action="store_true", help="Opt in to optional developer/debug regression through direct POST /runs using the frozen input.")
    parser.add_argument("--direct-regression-endpoint", default="/runs", help="Endpoint for optional direct debug regression, default: /runs")
    parser.add_argument("--skip-cache", action="store_true", help="Skip repeated library-run cache check")
    parser.add_argument("--mutate-seeded-tune", action="store_true", help="Patch seeded tune notes:null to verify null-clear behavior")
    parser.add_argument("--mutate-seeded-versions", action="store_true", help="Deprecate a pinned seeded version to test resolver warnings. Use only on a disposable dev DB.")
    parser.add_argument("--full-mutating", action="store_true", help="Run all mutation checks, including seeded tune and seeded pinned-version deprecation. Use only on a fresh dev DB.")
    parser.add_argument("--no-cleanup-created", action="store_true", help="Do not archive forked CVT/output objects created by this test")
    parser.add_argument(
        "--eviction-endpoint-template",
        default=None,
        help="Optional debug/admin eviction endpoint template, e.g. '/debug/runs/{run_id}/evict-full-result'. Not used by default because V1 has no public endpoint.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    harness = BlackBoxHarness(args)
    harness.run_all()


if __name__ == "__main__":
    main()
