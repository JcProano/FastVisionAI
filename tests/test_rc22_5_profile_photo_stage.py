import inspect
import unittest

from src.ui.photo_capture.controller import PersonPhotoController
from src.ui.tk_app import LocalFaceTkApp


class RC225ProfilePhotoStageTests(unittest.TestCase):
    def test_completed_enrollment_offers_photo_or_skip(self):
        source = inspect.getsource(LocalFaceTkApp.show_result)

        self.assertIn("REGISTRO FACIAL COMPLETADO", source)
        self.assertIn("CONTINUAR A FOTO DE PERFIL", source)
        self.assertIn("_continue_profile_photo(dto.person_id)", source)
        self.assertIn('text="OMITIR"', source)
        self.assertIn("command=self._skip_profile_photo", source)

    def test_photo_window_exposes_the_required_review_actions(self):
        source = inspect.getsource(LocalFaceTkApp.show_person_photo_capture)

        self.assertIn("Ahora puede tomar una fotografía para el perfil", source)
        for label in ("TOMAR FOTO", "REPETIR", "USAR ESTA FOTO", "OMITIR"):
            self.assertIn(label, source)
        self.assertIn("dto.review and dto.image_bytes", source)
        self.assertIn("state=\"normal\" if dto.review else \"disabled\"", source)

    def test_retake_discards_only_the_pending_preview(self):
        source = inspect.getsource(LocalFaceTkApp._retake_person_photo)

        self.assertIn("self._photo_capture_image = None", source)
        self.assertIn("self._on_retake_photo()", source)
        self.assertNotIn("save(", source)

    def test_existing_photo_requires_explicit_replacement_confirmation(self):
        source = inspect.getsource(LocalFaceTkApp.show_person_photo_capture)

        self.assertIn("dto.replace_existing", source)
        self.assertIn("messagebox.askyesno", source)
        self.assertIn("¿Desea reemplazarla?", source)
        self.assertIn("self._on_cancel_photo()", source)

    def test_photo_capture_uses_the_shared_presented_frame(self):
        source = inspect.getsource(LocalFaceTkApp.show_rgb_frame)

        self.assertIn("_photo_capture_preview", source)
        self.assertIn("photo_preview.configure(image=photo", source)
        self.assertNotIn("VideoCapture", source)

    def test_photo_stage_does_not_touch_biometric_components(self):
        source = "\n".join((
            inspect.getsource(LocalFaceTkApp.show_result),
            inspect.getsource(LocalFaceTkApp.show_person_photo_capture),
            inspect.getsource(PersonPhotoController),
        ))

        for forbidden in (
            "ArcFace", "FaceMatcher", "embedding", "templates.save",
            "RecognitionService", "VideoCapture",
        ):
            self.assertNotIn(forbidden, source)

    def test_confirmed_photo_is_saved_only_through_thumbnail_manager(self):
        source = inspect.getsource(PersonPhotoController.save)

        self.assertIn("self.thumbnails.save", source)
        self.assertIn("replace=replace", source)


if __name__ == "__main__":
    unittest.main()
