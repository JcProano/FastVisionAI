"""Composition root for the FastAPI web presentation adapter."""

from __future__ import annotations

from dataclasses import dataclass

from .controller import WebDashboardController
from .http_server import WebDashboardServer


@dataclass(frozen=True, slots=True)
class WebDashboardComponents:
    controller: WebDashboardController
    server: WebDashboardServer


class WebDashboardContainer:
    @staticmethod
    def build(
        policy,
        frame_store,
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
        operational_state_provider=None,
        authorization=None,
        controller_type=WebDashboardController,
        server_type=WebDashboardServer,
        server_options=None,
    ) -> WebDashboardComponents:
        controller = controller_type(
            snapshot_provider,
            people=people,
            history=history,
            attendance=attendance,
            reports=reports,
            system_health=system_health,
            identity_provider=identity_provider,
            camera_provider=camera_provider,
            actions=actions,
            diagnostics_provider=diagnostics_provider,
            audit=audit,
            backups=backups,
            configuration=configuration,
            presentation_provider=presentation_provider,
            operational_state_provider=operational_state_provider,
            authorization=authorization,
        )
        server = server_type(
            policy,
            controller,
            frame_store,
            **(server_options or {}),
        )
        return WebDashboardComponents(controller, server)
