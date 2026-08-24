"""Read-model projections consumed by the dashboard SPA."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from urllib.parse import parse_qs

from src.camera.source_discovery import redact_url
from src.ui.people.contracts import PeopleSearchFiltersDTO


class WebDashboardQueryProjection:
    def __init__(
        self,
        snapshot_provider,
        *,
        presentation_provider,
        resources,
        action,
        people=None,
        history=None,
        attendance=None,
        reports=None,
        system_health=None,
        camera_provider=None,
        diagnostics_provider=None,
        audit=None,
        backups=None,
        configuration=None,
    ) -> None:
        self._snapshot_provider = snapshot_provider
        self._presentation_provider = presentation_provider
        self._resources = resources
        self._action = action
        self._people = people
        self._history = history
        self._attendance = attendance
        self._reports = reports
        self._system_health = system_health
        self._camera_provider = camera_provider or (lambda: {})
        self._diagnostics_provider = diagnostics_provider
        self._audit = audit
        self._backups = backups
        self._configuration = configuration

    def execute(self, path: str, query: str = "") -> dict[str, object]:
        if path == "/api/dashboard":
            return self.dashboard_payload()
        if path == "/api/presentation":
            return self._presentation_provider()
        if path == "/api/cameras":
            sources = self._action("cameras", default=())
            return {
                "cameras": tuple(self._camera_dto(item) for item in sources)
            }
        if path == "/api/people":
            return self._people_payload(
                parse_qs(query, keep_blank_values=False)
            )
        if path == "/api/attendance":
            return self._attendance_payload()
        if path == "/api/history":
            return self._history_payload()
        if path == "/api/reports":
            return self._reports_payload()
        if path in {"/api/system", "/api/diagnostics"}:
            return self._system_payload()
        if path == "/api/audit":
            return self._audit_payload()
        if path == "/api/backups":
            return self._backups_payload()
        if path == "/api/settings":
            return self._settings_payload()
        raise KeyError(path)

    def dashboard_payload(self) -> dict[str, object]:
        snapshot = self._snapshot_provider()
        people_summary = self._people_summary()
        camera = self._safe_camera()
        if snapshot is None:
            return {
                "available": False,
                "camera": camera.get("state", "DESCONECTADA"),
                "recognition": "N/D",
                "database": "N/D",
                "attendance": "N/D",
                "gallery": 0,
                "people_summary": people_summary,
                "statistics": {
                    "people_present": None,
                    "recognitions_today": None,
                    "check_ins_today": None,
                    "late_today": None,
                },
                "recent_recognitions": [],
                "recent_attendance": [],
                "presentation": self._presentation_provider(),
            }

        recognitions = []
        for item in snapshot.recent_recognitions:
            state = getattr(
                item, "recognition_state", "NOT_EVALUATED"
            ).upper()
            evaluated = getattr(item, "evaluated", state == "MATCH") is True
            recognitions.append(
                {
                    "photo": self._resources.photo_url(item.photo),
                    "name": item.display_name,
                    "time": item.local_time,
                    "similarity": item.similarity,
                    "state": _visual_state(state, evaluated),
                }
            )
        recent_attendance = [
            {
                "photo": self._resources.photo_url(item.photo),
                "name": item.display_name,
                "check_in": item.check_in_local,
                "check_out": item.check_out_local,
                "status": item.status,
            }
            for item in snapshot.recent_attendance
        ]
        people_summary["biometric_identities"] = snapshot.gallery_identities
        people_summary["without_face"] = max(
            0,
            people_summary["registered_people"]
            - snapshot.gallery_identities,
        )
        return {
            "available": True,
            "camera": snapshot.camera_state,
            "camera_name": camera.get("name", "N/D"),
            "camera_type": camera.get("type", "N/D"),
            "camera_source": camera.get("source", "N/D"),
            "recognition": snapshot.recognition_state,
            "database": snapshot.database_state,
            "attendance": snapshot.attendance_state,
            "gallery": snapshot.gallery_identities,
            "people_summary": people_summary,
            "statistics": {
                "people_present": snapshot.people_present,
                "recognitions_today": snapshot.recognitions_today,
                "check_ins_today": snapshot.check_ins_today,
                "late_today": snapshot.late_today,
            },
            "recent_recognitions": recognitions,
            "recent_attendance": recent_attendance,
            "presentation": self._presentation_provider(),
            "generated_at": snapshot.generated_at.isoformat(),
        }

    def _people_summary(self) -> dict[str, int]:
        empty = {
            "registered_people": 0,
            "biometric_identities": 0,
            "without_face": 0,
        }
        if self._people is None:
            return empty
        try:
            result = self._people.search(
                PeopleSearchFiltersDTO(
                    limit=self._people.policy.default_page_size
                )
            )
        except Exception:
            return empty
        return {
            "registered_people": result.total,
            "biometric_identities": 0,
            "without_face": result.total,
        }

    def _safe_camera(self) -> dict[str, str]:
        try:
            value = dict(self._camera_provider())
        except Exception:
            return _disconnected_camera()
        source = str(value.get("source", "N/D"))
        if source.lower().startswith(
            ("http://", "https://", "rtsp://", "rtsps://")
        ):
            source = redact_url(source)
        return {
            "state": str(value.get("state", "DESCONECTADA")),
            "name": str(value.get("name", "N/D")),
            "type": str(value.get("type", "N/D")),
            "source": source,
        }

    def _camera_dto(self, item) -> dict[str, object]:
        active = item.source_id == self._safe_camera().get("source")
        network = item.source_type.value != "LOCAL_V4L2"
        if active:
            status = "ACTIVA"
        elif not item.available:
            status = "OFFLINE"
        elif network:
            status = "NO COMPROBADA"
        else:
            status = "DISPONIBLE"
        return {
            "id": item.source_id,
            "name": item.display_name,
            "type": item.source_type.value,
            "available": item.available,
            "preferred": item.preferred,
            "active": active,
            "network": network,
            "status": status,
            "details": dict(item.details),
        }

    def _people_payload(self, query) -> dict[str, object]:
        if self._people is None:
            return {"people": (), "total": 0}
        text = str(query.get("q", [""])[0])[:100]
        value = self._people.search(
            PeopleSearchFiltersDTO(
                text=text, limit=self._people.policy.default_page_size
            )
        )
        people = []
        for item in value.people:
            token = self._resources.person_token(item.person_id)
            people.append(
                {
                    "token": token,
                    "name": item.display_name,
                    "first_name": item.first_name,
                    "last_name": item.last_name,
                    "cedula": item.masked_cedula,
                    "phone": item.phone,
                    "email": item.email,
                    "status": item.status,
                    "biometrics": (
                        "SIN ROSTRO REGISTRADO"
                        if item.template_count == 0
                        else f"{item.template_count} TEMPLATES"
                    ),
                    "thumbnail": (
                        f"/api/thumbnails/{token}"
                        if item.thumbnail_available
                        else None
                    ),
                }
            )
        return {"people": people, "total": value.total}

    def _attendance_payload(self) -> dict[str, object]:
        values = (
            ()
            if self._attendance is None
            else self._attendance.day_list().days
        )
        return {
            "attendance": [
                {
                    "name": item.display_name,
                    "date": item.local_date.isoformat(),
                    "status": item.status,
                    "check_in": _time(item.check_in),
                    "check_out": _time(item.check_out),
                }
                for item in values
            ]
        }

    def _history_payload(self) -> dict[str, object]:
        values = (
            () if self._history is None else self._history.list(limit=100).events
        )
        return {
            "events": [
                {
                    "name": item.display_name,
                    "time": item.timestamp.isoformat(),
                    "type": item.event_type,
                    "similarity": item.similarity,
                    "camera": (
                        redact_url(item.camera_id)
                        if isinstance(item.camera_id, str)
                        else item.camera_id
                    ),
                }
                for item in values
            ]
        }

    def _reports_payload(self) -> dict[str, object]:
        if self._reports is None:
            return {"available": False}
        _start, end = self._reports.default_dates()
        value = self._reports.generate("Resumen diario", end, end)
        return {
            "available": True,
            "date": str(end),
            "report": plain_dto(value),
        }

    def _system_payload(self) -> dict[str, object]:
        if self._diagnostics_provider is not None:
            try:
                return plain_dto(self._diagnostics_provider())
            except Exception:
                return {"available": False}
        if self._system_health is None:
            return {"available": False}
        value = self._system_health.snapshot()
        return {
            "available": True,
            "overall": value.overall_level,
            "components": [
                {
                    "name": part[0],
                    "level": part[1],
                    "message": part[2],
                    "checked": str(part[3]),
                }
                for part in value.components
            ],
        }

    def _audit_payload(self) -> dict[str, object]:
        if self._audit is None:
            return {"available": False}
        value = self._audit.query()
        return {
            "available": True,
            "events": [plain_dto(item) for item in value.records],
        }

    def _backups_payload(self) -> dict[str, object]:
        if self._backups is None:
            return {"available": False}
        return {
            "available": True,
            "operations": [
                plain_dto(item) for item in self._backups.history()
            ],
        }

    def _settings_payload(self) -> dict[str, object]:
        if self._configuration is None:
            return {"available": False}
        value = self._configuration.current().as_mapping()
        return {"available": True, "settings": _redacted_settings(value)}


def plain_dto(value):
    if dataclasses.is_dataclass(value):
        return {
            field.name: plain_dto(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if _safe_key(field.name)
        }
    if isinstance(value, dict):
        return {
            str(key): plain_dto(item)
            for key, item in value.items()
            if _safe_key(str(key))
        }
    if isinstance(value, (tuple, list)):
        return [plain_dto(item) for item in value]
    return _plain(value)


def _disconnected_camera() -> dict[str, str]:
    return {
        "state": "DESCONECTADA",
        "name": "N/D",
        "type": "N/D",
        "source": "N/D",
    }


def _visual_state(state, evaluated):
    if state == "MATCH" and evaluated:
        return "IDENTIFICADO"
    if state == "UNKNOWN" and evaluated:
        return "NO REGISTRADA"
    return "NO EVALUADO"


def _time(value):
    return None if value is None else value.isoformat()


def _safe_key(key):
    forbidden = (
        "person_id",
        "embedding",
        "template",
        "password",
        "hash",
        "salt",
        "path",
    )
    return not any(word in key.lower() for word in forbidden)


def _plain(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return len(value)
    return str(value)


def _redacted_settings(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(
                part in lowered
                for part in (
                    "embedding",
                    "template",
                    "hash",
                    "password",
                    "secret",
                    "salt",
                )
            ):
                continue
            result[key] = (
                redact_url(str(item))
                if lowered == "url"
                else _redacted_settings(item)
            )
        return result
    if isinstance(value, list):
        return [_redacted_settings(item) for item in value]
    return value
