"""HTTP-agnostic command/query facade used by the FastAPI adapter."""

from __future__ import annotations

import json
import time

from src.core.security import AuthorizationPermission
from src.core.web_dashboard import WebEnrollmentContainer

from .presentation_projection import WebPresentationProjection
from .query_projection import WebDashboardQueryProjection, plain_dto
from .resource_tokens import WebResourceTokenStore


QUERY_PERMISSIONS = {
    "/api/dashboard": AuthorizationPermission.VIEW_DASHBOARD,
    "/api/presentation": AuthorizationPermission.VIEW_DASHBOARD,
    "/api/enrollment/status": AuthorizationPermission.ENROLL_PERSON,
    "/api/cameras": AuthorizationPermission.VIEW_DASHBOARD,
    "/api/people": AuthorizationPermission.VIEW_PEOPLE,
    "/api/attendance": AuthorizationPermission.VIEW_ATTENDANCE,
    "/api/history": AuthorizationPermission.VIEW_DETECTION_HISTORY,
    "/api/reports": AuthorizationPermission.VIEW_REPORTS,
    "/api/system": AuthorizationPermission.VIEW_SYSTEM_HEALTH,
    "/api/diagnostics": AuthorizationPermission.VIEW_SYSTEM_HEALTH,
    "/api/audit": AuthorizationPermission.VIEW_AUDIT,
    "/api/backups": AuthorizationPermission.BACKUP,
    "/api/settings": AuthorizationPermission.VIEW_SETTINGS,
}

ACTION_ROUTES = {
    "/api/camera/select": "camera_select",
    "/api/camera/connect": "camera_select",
    "/api/camera/preferred": "camera_preferred",
    "/api/camera/network": "camera_network",
    "/api/camera/network/edit": "camera_network_update",
    "/api/camera/probe": "camera_probe",
    "/api/camera/network/delete": "camera_network_delete",
    "/api/person/update": "person_update",
    "/api/person/delete": "person_delete",
    "/api/person/photo": "person_photo",
    "/api/person/face": "person_face",
    "/api/enrollment/start": "enrollment_start",
    "/api/enrollment/person": "enrollment_person",
    "/api/enrollment/capture/start": "enrollment_capture_start",
    "/api/enrollment/cancel": "enrollment_cancel",
    "/api/enrollment/photo": "enrollment_photo",
    "/api/enrollment/confirm": "enrollment_confirm",
    "/api/presentation/ignore": "presentation_ignore",
    "/api/attendance/manual": "attendance_manual",
    "/api/backups": "backup_create",
    "/api/shutdown": "shutdown",
}

ACTION_PERMISSIONS = {
    "camera_select": AuthorizationPermission.VIEW_DASHBOARD,
    "camera_preferred": AuthorizationPermission.VIEW_DASHBOARD,
    "camera_network": AuthorizationPermission.VIEW_DASHBOARD,
    "camera_network_update": AuthorizationPermission.VIEW_DASHBOARD,
    "camera_probe": AuthorizationPermission.VIEW_DASHBOARD,
    "camera_network_delete": AuthorizationPermission.VIEW_DASHBOARD,
    "person_update": AuthorizationPermission.EDIT_PERSON,
    "person_delete": AuthorizationPermission.EDIT_PERSON,
    "person_photo": AuthorizationPermission.ENROLL_PERSON,
    "person_face": AuthorizationPermission.ENROLL_PERSON,
    "enrollment_start": AuthorizationPermission.ENROLL_PERSON,
    "enrollment_person": AuthorizationPermission.ENROLL_PERSON,
    "enrollment_capture_start": AuthorizationPermission.ENROLL_PERSON,
    "enrollment_cancel": AuthorizationPermission.ENROLL_PERSON,
    "enrollment_photo": AuthorizationPermission.ENROLL_PERSON,
    "enrollment_confirm": AuthorizationPermission.ENROLL_PERSON,
    "presentation_ignore": AuthorizationPermission.VIEW_DASHBOARD,
    "attendance_manual": AuthorizationPermission.MANUAL_ATTENDANCE,
    "backup_create": AuthorizationPermission.BACKUP,
    "shutdown": AuthorizationPermission.APPLICATION_EXIT,
}


class WebDashboardController:
    """Authorize and dispatch the dashboard's explicit commands and queries."""

    def __init__(
        self,
        snapshot_provider,
        *,
        people=None,
        history=None,
        attendance=None,
        reports=None,
        system_health=None,
        identity_provider=None,
        camera_provider=None,
        actions=None,
        diagnostics_provider=None,
        audit=None,
        backups=None,
        configuration=None,
        presentation_provider=None,
        monotonic=time.monotonic,
        modal_timeout_seconds: float = 60.0,
        operational_state_provider=None,
        authorization=None,
        resource_tokens=None,
    ) -> None:
        self.actions = actions or {}
        self.authorization = authorization
        self._resources = resource_tokens or WebResourceTokenStore(
            identity_provider
        )
        self._presentation = WebPresentationProjection(
            presentation_provider=presentation_provider,
            operational_state_provider=operational_state_provider,
            identity_provider=identity_provider,
            resources=self._resources,
            monotonic=monotonic,
            timeout_seconds=modal_timeout_seconds,
        )
        self._queries = WebDashboardQueryProjection(
            snapshot_provider,
            presentation_provider=self._presentation.payload,
            resources=self._resources,
            action=self._action,
            people=people,
            history=history,
            attendance=attendance,
            reports=reports,
            system_health=system_health,
            camera_provider=camera_provider,
            diagnostics_provider=diagnostics_provider,
            audit=audit,
            backups=backups,
            configuration=configuration,
        )
        self._enrollment = WebEnrollmentContainer.build(
            submit_person=lambda payload: self._action(
                "enrollment_person", payload
            ),
            begin_capture=lambda payload: self._action(
                "enrollment_capture_start", payload
            ),
            start_photo=lambda payload: self._action(
                "enrollment_photo_start", payload
            ),
            capture_photo=lambda payload: self._action(
                "enrollment_photo_capture", payload
            ),
            confirm_photo=lambda payload: self._action(
                "enrollment_photo_confirm", payload
            ),
            cancel=lambda payload: self._action("enrollment_cancel", payload),
            get_status=lambda: self._action(
                "enrollment_status", default=None
            ),
        )

    def dashboard_payload(self) -> dict[str, object]:
        return self._queries.dashboard_payload()

    def json_bytes(self) -> bytes:
        return json.dumps(
            self.dashboard_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def api(self, path: str, query: str = "") -> dict[str, object]:
        permission = QUERY_PERMISSIONS.get(path)
        if permission is None:
            raise KeyError(path)
        self._require(permission)
        if path == "/api/enrollment/status":
            return self._enrollment.get_status.execute()
        return self._queries.execute(path, query)

    def action(
        self, path: str, payload: dict[str, object]
    ) -> dict[str, object]:
        key = ACTION_ROUTES.get(path)
        if key is None:
            raise KeyError(path)
        self._require(ACTION_PERMISSIONS[key])

        if key == "camera_network_delete":
            value = self._delete_camera(payload)
        elif key.startswith("person_"):
            value = self._person_action(key, payload)
        elif key == "presentation_ignore":
            self._presentation.dismiss()
            value = True
        elif key == "enrollment_start":
            current = self._presentation.payload()
            self._enrollment.start.execute(str(current.get("kind", "")))
            value = True
        elif key == "enrollment_person":
            value = self._enrollment.submit_person.execute(payload)
        elif key == "enrollment_capture_start":
            value = self._enrollment.begin_capture.execute(payload)
        elif key == "enrollment_photo":
            value = self._enrollment.select_photo.execute(
                str(payload.get("action", "")), payload
            )
        elif key == "enrollment_confirm":
            value = self._enrollment.confirm.execute()
        elif key == "enrollment_cancel":
            value = self._enrollment.cancel.execute(payload)
        else:
            value = self._action(key, payload)
        return {"ok": True, "result": plain_dto(value)}

    def delete(self, _path: str) -> dict[str, object]:
        raise ValueError(
            "La eliminación requiere confirmación JSON explícita."
        )

    def thumbnail(self, token: str) -> tuple[str, bytes] | None:
        return self._resources.thumbnail(token)

    def _person_token(self, person_id: str) -> str:
        """Compatibility helper for callers that build a person action DTO."""
        return self._resources.person_token(person_id)

    def _presentation_payload(self) -> dict[str, object]:
        """Compatibility helper for focused presentation tests."""
        return self._presentation.payload()

    def _delete_camera(self, payload: dict[str, object]):
        if payload.get("confirmed") is not True:
            raise ValueError("Se requiere confirmación.")
        source_id = str(payload.get("source_id", ""))
        if not source_id or "/" in source_id:
            raise ValueError("Identificador inválido.")
        return self._action("camera_network_delete", source_id)

    def _person_action(self, key: str, payload: dict[str, object]):
        token = str(payload.get("token", ""))
        person_id = self._resources.resolve_person(token)
        if key != "person_delete":
            return self._action(key, person_id, payload)
        if (
            payload.get("confirmed") is not True
            or payload.get("confirmation") != "ELIMINAR"
        ):
            raise ValueError("Se requiere confirmación reforzada.")
        return self._action(key, person_id, True)

    def _action(self, name, *args, default=None):
        callback = self.actions.get(name)
        return default if callback is None else callback(*args)

    def _require(self, permission: AuthorizationPermission) -> None:
        if self.authorization is None:
            return
        if not self.authorization.require(permission).allowed:
            raise PermissionError("operation is not authorized")
