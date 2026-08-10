import dataclasses
import inspect
import unittest
from datetime import datetime, timezone

from src.engine.action_executor import (
    ActionExecutionContext, ExecutableAction, PopupActionData,
)
from src.ui.action_adapters import IdentificationPopupActionAdapter
from src.ui.identification import (
    IdentificationPopupPolicy, IdentificationPopupType,
    IdentificationPresentationController, IdentityPersonDTO,
)
from src.ui.thumbnails import ThumbnailDTO


class Provider:
    def __init__(self): self.person_calls = []; self.thumbnail_calls = []
    def get_person(self, person_id):
        self.person_calls.append(person_id)
        return IdentityPersonDTO(
            person_id, "Temporary", "Person", "Temporary Person", "EXT-1",
            address="Safe address", status="ACTIVE",
        )
    def get_thumbnail(self, person_id):
        self.thumbnail_calls.append(person_id)
        return ThumbnailDTO(person_id, True, 32, 32, "jpeg", b"safe")


def context(action, person_id=None):
    return ActionExecutionContext(
        action, person_id, "run", "session", "POLICY_ELIGIBLE",
        datetime.now(timezone.utc),
    )


class PopupActionAdapterTests(unittest.TestCase):
    def controller(self, provider=None, *, frames=1, clock=None):
        return IdentificationPresentationController(
            IdentificationPopupPolicy(True, 10, 10, frames, 60), provider or Provider(),
            monotonic=(lambda: 0.0 if clock is None else clock[0]),
        )

    def test_registered_resolves_person_and_thumbnail_only_in_controller(self):
        provider = Provider(); adapter = IdentificationPopupActionAdapter(
            self.controller(provider))
        adapter.show_registered(
            context(ExecutableAction.SHOW_REGISTERED_POPUP, "person"),
            PopupActionData("NOT_EVALUATED", .91),
        )
        dto = adapter.drain()[0]
        self.assertEqual(dto.popup_type, IdentificationPopupType.REGISTERED_CANDIDATE)
        self.assertEqual(dto.display_name, "Temporary Person")
        self.assertEqual(dto.external_identifier, "EXT-1")
        self.assertTrue(dto.thumbnail_available)
        self.assertEqual(provider.person_calls, ["person"])
        self.assertEqual(provider.thumbnail_calls, ["person"])

    def test_unregistered_has_no_civil_resolution_or_reservation(self):
        provider = Provider(); adapter = IdentificationPopupActionAdapter(
            self.controller(provider))
        adapter.show_unregistered(
            context(ExecutableAction.SHOW_UNREGISTERED_POPUP),
            PopupActionData("NO_GALLERY", message="No existe candidato local"),
        )
        dto = adapter.drain()[0]
        self.assertEqual(dto.popup_type, IdentificationPopupType.UNREGISTERED)
        self.assertEqual(dto.message, "No existe candidato local")
        self.assertEqual(provider.person_calls, [])

    def test_candidate_stability_and_cooldowns_remain_in_controller(self):
        clock = [0.0]; controller = self.controller(frames=2, clock=clock)
        adapter = IdentificationPopupActionAdapter(controller)
        general = context(ExecutableAction.SHOW_REGISTERED_POPUP, "person")
        popup = PopupActionData("NOT_EVALUATED", .8)
        adapter.show_registered(general, popup)
        adapter.show_registered(general, popup)
        adapter.show_registered(general, popup)
        values = adapter.drain()
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].popup_type, IdentificationPopupType.REGISTERED_CANDIDATE)

    def test_bounded_queue_keeps_recent_and_clear_close_are_safe(self):
        adapter = IdentificationPopupActionAdapter(self.controller(), queue_size=1)
        general = context(ExecutableAction.SHOW_UNREGISTERED_POPUP)
        adapter.show_unregistered(general, PopupActionData("NO_GALLERY", message="first"))
        adapter.show_unregistered(general, PopupActionData("NO_GALLERY", message="recent"))
        values = adapter.drain()
        self.assertEqual(len(values), 1); self.assertEqual(values[0].message, "recent")
        adapter.show_unregistered(general, PopupActionData("NO_GALLERY"))
        adapter.clear(); self.assertEqual(adapter.drain(), ())
        adapter.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            adapter.show_unregistered(general, PopupActionData("NO_GALLERY"))

    def test_contract_is_pii_free_and_adapter_never_imports_tkinter(self):
        self.assertEqual(
            {field.name for field in dataclasses.fields(PopupActionData)},
            {"recognition_state", "similarity", "message"},
        )
        forbidden = {"name", "cedula", "external_identifier", "address", "phone",
                     "email", "thumbnail", "embedding", "template", "array", "model"}
        self.assertFalse({field.name for field in dataclasses.fields(PopupActionData)} &
                         forbidden)
        source = inspect.getsource(__import__(
            "src.ui.action_adapters.popup_adapter", fromlist=["unused"]))
        self.assertNotIn("tkinter", source)


if __name__ == "__main__":
    unittest.main()
