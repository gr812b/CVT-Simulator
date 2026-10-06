"""Authenticated saves, revision history and Build a run input persistence."""

from copy import deepcopy

from fastapi.testclient import TestClient


def template(client, kind):
    response = client.get(f"/api/v1/physical-library/templates/{kind}")
    assert response.status_code == 200, response.text
    return response.json()["document"]


def save_physical(client, document, previous=None):
    path = f"/api/v1/physical-library/items/{document['kind']}"
    if previous is not None:
        response = client.put(
            f"{path}/{previous['item']['id']}",
            json={
                "document": document,
                "expected_revision_id": previous["item"]["revision_id"],
            },
        )
        assert response.status_code == 200, response.text
    else:
        response = client.post(path, json={"document": document, "expected_revision_id": None})
        assert response.status_code == 201, response.text
    return response.json()


def test_registration_csrf_origin_and_session_rotation(api, register):
    assert api.get("/api/v1/auth/session").status_code == 401
    registration = {
        "email": "driver@example.com",
        "display_name": "Driver",
        "password": "local-test-password",
    }
    missing_header = api.post("/api/v1/auth/register", json=registration)
    assert missing_header.status_code == 403
    assert missing_header.json()["error"]["code"] == "client_header_required"
    bad_origin = api.post(
        "/api/v1/auth/register",
        json=registration,
        headers={"X-Cinder-Client": "web", "Origin": "https://unrelated.example"},
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error"]["code"] == "origin_not_allowed"

    identity = register(api)
    session = api.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json() == identity
    assert session.headers["cache-control"] == "no-store"
    cookie = api.cookies.get("cinder_session")
    assert cookie
    document = template(api, "engines")
    payload = {"document": document, "expected_revision_id": None}
    for headers, error in (
        ({"X-CSRF-Token": ""}, "csrf_invalid"),
        ({"X-CSRF-Token": "wrong-token"}, "csrf_invalid"),
        ({"X-Cinder-Client": ""}, "client_header_required"),
        ({"Origin": "https://unrelated.example"}, "origin_not_allowed"),
    ):
        rejected = api.post("/api/v1/physical-library/items/engines", json=payload, headers=headers)
        assert rejected.status_code == 403, rejected.text
        assert rejected.json()["error"]["code"] == error
    assert api.get("/api/v1/physical-library/items/engines?scope=own").json()["items"] == []

    logged_in = api.post(
        "/api/v1/auth/login",
        json={"email": registration["email"], "password": registration["password"]},
    )
    assert logged_in.status_code == 200, logged_in.text
    replacement = logged_in.json()
    assert replacement["account"]["id"] == identity["account"]["id"]
    assert api.cookies.get("cinder_session") != cookie
    assert replacement["csrf_token"] != identity["csrf_token"]
    stale = api.post("/api/v1/physical-library/items/engines", json=payload)
    assert stale.status_code == 403
    api.headers["X-CSRF-Token"] = replacement["csrf_token"]
    assert save_physical(api, document)["detail"]["item"]["owned"] is True
    assert api.post("/api/v1/auth/logout").status_code == 200
    assert api.get("/api/v1/auth/session").status_code == 401


def test_physical_save_noop_history_conflict_restore_and_archive(signed_in):
    client = signed_in
    document = template(client, "engines")
    document["name"] = "Test engine"
    first = save_physical(client, document)["detail"]
    unchanged = save_physical(client, first["document"], first)
    assert unchanged["changed"] is False
    assert len(unchanged["detail"]["history"]) == 1

    edited = deepcopy(first["document"])
    edited["data"]["equivalent_rotational_inertia_kg_m2"] = 0.35
    second = save_physical(client, edited, first)["detail"]
    assert second["item"]["revision_number"] == 2
    assert second["item"]["revision_id"] != first["item"]["revision_id"]
    path = f"/api/v1/physical-library/items/engines/{first['item']['id']}"
    original = client.get(path, params={"revision_id": first["item"]["revision_id"]})
    assert original.status_code == 200
    assert original.json()["document"] == first["document"]
    stale = client.put(
        path, json={"document": document, "expected_revision_id": first["item"]["revision_id"]}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"

    comparison = client.get(
        f"{path}/compare",
        params={
            "from_revision_id": first["item"]["revision_id"],
            "to_revision_id": second["item"]["revision_id"],
        },
    )
    assert comparison.status_code == 200
    assert any(
        "equivalent_rotational_inertia_kg_m2" in difference["path"]
        for difference in comparison.json()["differences"]
    )
    restored = client.post(
        f"{path}/restore",
        json={
            "expected_revision_id": second["item"]["revision_id"],
            "revision_id": first["item"]["revision_id"],
        },
    )
    assert restored.status_code == 200, restored.text
    third = restored.json()["detail"]
    assert third["document"] == first["document"]
    assert third["item"]["revision_number"] == 3
    archived = client.post(
        f"{path}/archive",
        json={"expected_revision_id": third["item"]["revision_id"], "archived": True},
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert client.get("/api/v1/physical-library/items/engines?scope=own").json()["items"] == []
    assert (
        client.get(path, params={"revision_id": first["item"]["revision_id"]}).json()["document"]
        == first["document"]
    )


def test_public_read_and_copy_never_grant_write_ownership(signed_in, register):
    owner = signed_in
    original = save_physical(owner, template(owner, "engines"))["detail"]
    path = f"/api/v1/physical-library/items/engines/{original['item']['id']}"
    with TestClient(owner.app) as other:
        public = other.get(path)
        assert public.status_code == 200
        assert public.json()["item"]["owned"] is False
        payload = {
            "document": original["document"],
            "expected_revision_id": original["item"]["revision_id"],
        }
        assert other.put(path, json=payload).status_code == 401
        register(other, email="other@example.com", name="Other driver")
        assert other.put(path, json=payload).status_code == 404
        copied = other.post(
            f"/api/v1/physical-library/revisions/engines/{original['item']['revision_id']}/copy",
            json={"name": "My copy"},
        )
        assert copied.status_code == 201, copied.text
        copy_detail = copied.json()
        assert copy_detail["item"]["owned"] is True
        assert copy_detail["item"]["id"] != original["item"]["id"]
        assert copy_detail["document"]["data"] == original["document"]["data"]
    assert owner.get(path).json()["document"] == original["document"]


def test_setup_save_keeps_unchanged_references_and_copies_an_edited_sample(signed_in):
    client = signed_in
    document = template(client, "setups")
    source = deepcopy(document["data"])
    first = save_physical(client, document)["detail"]
    assert first["document"]["data"]["engine"]["revision_id"] == source["engine"]["revision_id"]
    assert first["document"]["data"]["cvt"]["revision_id"] == source["cvt"]["revision_id"]
    assert client.get("/api/v1/physical-library/items/engines?scope=own").json()["items"] == []
    edited = deepcopy(first["document"])
    edited["data"]["engine"]["data"]["equivalent_rotational_inertia_kg_m2"] = 0.35
    second = save_physical(client, edited, first)["detail"]
    assert second["document"]["data"]["engine"]["revision_id"] != source["engine"]["revision_id"]
    assert second["document"]["data"]["cvt"]["revision_id"] == source["cvt"]["revision_id"]
    owned_engines = client.get("/api/v1/physical-library/items/engines?scope=own").json()["items"]
    assert len(owned_engines) == 1
    source_again = template(client, "setups")["data"]["engine"]
    assert source_again == source["engine"]
    assert len(second["history"]) == 2


def test_saved_tune_revision_survives_setup_save_preview_and_queue(signed_in):
    client = signed_in
    setup = template(client, "setups")
    cvt_revision = setup["data"]["cvt"]["revision_id"]
    surface = client.get(f"/api/v1/experiments/tuning/{cvt_revision}").json()
    assert surface["default_tune"]["item"]["owned"] is False
    tune = deepcopy(surface["template"])
    tune["name"] = "Saved tip mass"
    tune["values"]["primary_tip_mass"] = 0.3
    created = client.post(
        "/api/v1/experiments/items", json={"document": tune, "expected_revision_id": None}
    )
    assert created.status_code == 201, created.text
    first = created.json()["detail"]
    assert first["item"]["owned"] is True
    tune["values"]["primary_tip_mass"] = 0.45
    updated = client.put(
        f"/api/v1/experiments/items/{first['item']['id']}",
        json={"document": tune, "expected_revision_id": first["item"]["revision_id"]},
    )
    assert updated.status_code == 200, updated.text
    latest = updated.json()["detail"]
    assert latest["item"]["revision_number"] == 2
    setup["data"]["engine"]["data"]["equivalent_rotational_inertia_kg_m2"] = 0.35
    saved_setup = save_physical(client, setup)["detail"]
    selection = {
        "setup_revision_id": saved_setup["item"]["revision_id"],
        "tune_revision_id": latest["item"]["revision_id"],
    }
    preview = client.post("/api/v1/experiments/preview", json=selection)
    assert preview.status_code == 200, preview.text
    assert preview.json()["validation"]["is_valid"] is True
    provenance = preview.json()["provenance"]
    assert provenance["tune_revision_id"] == latest["item"]["revision_id"]
    assert provenance["tune_values"]["primary_tip_mass"] == 0.45
    assert provenance["tune_unsaved"] is False
    queued = client.post(
        "/api/v1/experiments/runs", json={**selection, "request_key": "saved-tune-journey-request"}
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "queued"
    run_id = queued.json()["id"]
    frozen = client.get(f"/api/v1/runs/{run_id}/input").json()
    assert frozen["run"]["provenance"]["tune_revision_id"] == latest["item"]["revision_id"]
    assert frozen["run"]["provenance"]["tune_values"]["primary_tip_mass"] == 0.45
    assert frozen["input_document_snapshot"] == preview.json()["simulation_case"]
    assert (
        frozen["input_document_snapshot"]["shaft_boundaries"]["primary"][
            "equivalent_rotational_inertia_kg_m2"
        ]
        == 0.35
    )
    old = client.get(
        f"/api/v1/experiments/items/{first['item']['id']}/detail",
        params={"revision_id": first["item"]["revision_id"]},
    )
    assert old.status_code == 200
    assert old.json()["document"]["values"]["primary_tip_mass"] == 0.3
    assert client.post(f"/api/v1/runs/{run_id}/cancel").json()["status"] == "cancelled"
