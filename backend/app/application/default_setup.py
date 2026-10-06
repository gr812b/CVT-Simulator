"""Resolve an accessible baseline for a new validation workspace."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application import access
from app.application.auth import Principal
from app.core.errors import ApiProblem
from app.database.models import ExecutionPreset, LoadCase, VehicleAssembly
from app.database.resolver import resolve_simulation_case
from app.schemas.simulation_cases import ResolveLibrarySimulationCaseRequest


def initial_validation_case(session: Session, principal: Principal) -> dict:
    assemblies = session.scalars(
        select(VehicleAssembly)
        .where(
            (VehicleAssembly.account_id == principal.account_id)
            | (VehicleAssembly.visibility == "public"),
            VehicleAssembly.deleted_at.is_(None),
            VehicleAssembly.released_version_id.is_not(None),
        )
        .order_by(VehicleAssembly.is_default.desc(), VehicleAssembly.catalog_priority.desc())
    )
    load = session.scalar(
        select(LoadCase)
        .where(
            (LoadCase.account_id == principal.account_id) | (LoadCase.visibility == "public"),
            LoadCase.deleted_at.is_(None),
        )
        .order_by(LoadCase.created_at, LoadCase.id)
    )
    execution = session.scalar(
        select(ExecutionPreset)
        .where(
            ExecutionPreset.account_id.is_(None),
            ExecutionPreset.is_system_default.is_(True),
        )
        .order_by(ExecutionPreset.created_at, ExecutionPreset.id)
    )
    if load is not None and execution is not None:
        for assembly in assemblies:
            selection = ResolveLibrarySimulationCaseRequest(
                vehicle_assembly_version_id=assembly.released_version_id,
                load_case_id=load.id,
                execution_preset_id=execution.id,
            )
            try:
                access.run_selection(session, principal, selection)
            except ApiProblem:
                continue
            return resolve_simulation_case(session, **selection.model_dump())
    raise ApiProblem(
        422,
        "validation_workspace_unavailable",
        "No complete vehicle baseline is available yet. Ask an administrator to add the sample catalog.",
    )
