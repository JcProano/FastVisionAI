from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from src.core.configuration import ConfigurationProfile, ConfigurationValidator
from src.core.person_database import PersonRepository, PersonStatus
from src.ui.main import (
    build_thumbnail_manager, load_startup_gallery,
    storage_synchronization_diagnostic,
)


ROOT = Path(__file__).resolve().parents[1]
PERSON_ID = "64308b40-2636-4737-8523-e070ade05331"
NAMESPACE_ERROR = (
    "La base de personas, la galería biométrica y los thumbnails deben pertenecer "
    "al mismo namespace de datos."
)


def load_profile(name: str) -> dict[str, object]:
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RC16StorageNamespaceTests(unittest.TestCase):
    def test_profiles_use_one_explicit_namespace(self):
        expected = {
            "local_face_validation.pc.json": "data/fastvision",
            "local_face_validation.dev.json": "data/ui_validation",
            "local_face_validation.prod.json": "data/fastvision",
            "local_face_validation.jetson.json": "data/fastvision",
        }
        for filename, namespace in expected.items():
            with self.subTest(filename=filename):
                value = load_profile(filename)
                self.assertEqual(value["data_namespace"]["root"], namespace)
                self.assertEqual(Path(value["person_database"]["path"]).parent, Path(namespace))
                self.assertEqual(Path(value["persistence"]["directory"]).parts[:2], Path(namespace).parts)
                self.assertEqual(Path(value["thumbnails"]["directory"]).parts[:2], Path(namespace).parts)

    def test_mixed_explicit_and_legacy_namespaces_fail_but_coherent_legacy_passes(self):
        validator = ConfigurationValidator(ROOT)
        coherent = {
            "person_database": {"path": "data/temporary/people.db"},
            "persistence": {"directory": "data/temporary/gallery"},
            "thumbnails": {"directory": "data/temporary/thumbnails"},
        }
        self.assertTrue(validator.validate(coherent, ConfigurationProfile.DEVELOPMENT).valid)
        mixed = json.loads(json.dumps(coherent))
        mixed["thumbnails"]["directory"] = "data/other/thumbnails"
        result = validator.validate(mixed, ConfigurationProfile.DEVELOPMENT)
        self.assertFalse(result.valid)
        self.assertIn(NAMESPACE_ERROR, {issue.message for issue in result.errors})
        explicit = json.loads(json.dumps(coherent)); explicit["data_namespace"] = {"root": "data/other"}
        self.assertFalse(validator.validate(explicit, ConfigurationProfile.DEVELOPMENT).valid)

    def test_pc_loads_real_active_person_five_templates_and_thumbnail_without_mutation(self):
        profile = load_profile("local_face_validation.pc.json")
        manifest = ROOT / "data/fastvision/gallery/gallery.json"
        archive = ROOT / "data/fastvision/gallery/gallery.npz"
        before = (digest(manifest), digest(archive))
        repository = PersonRepository(ROOT / profile["person_database"]["path"])
        person = repository.get_by_person_id(PERSON_ID)
        self.assertIsNotNone(person); self.assertIs(person.status, PersonStatus.ACTIVE)
        startup = load_startup_gallery(profile, project_root=ROOT)
        self.assertIsNone(startup.error)
        self.assertEqual(len(startup.gallery.list_identities()), 1)
        self.assertEqual(len(startup.gallery.templates(PERSON_ID)), 5)
        diagnostic = storage_synchronization_diagnostic(
            repository, startup.gallery, gallery_loaded=True,
        )
        self.assertTrue(diagnostic.gallery_loaded)
        self.assertEqual(diagnostic.identity_count, 1)
        self.assertEqual(diagnostic.template_count, 5)
        self.assertEqual(diagnostic.active_person_count, 1)
        self.assertEqual(diagnostic.matched_person_ids, (PERSON_ID,))
        self.assertTrue(diagnostic.synchronization_ok)
        thumbnail = build_thumbnail_manager(profile, ROOT).load(PERSON_ID)
        self.assertTrue(thumbnail.image_bytes)
        self.assertEqual((digest(manifest), digest(archive)), before)

    def test_pc_load_and_recognition_policies_are_explicitly_non_decisional(self):
        profile = load_profile("local_face_validation.pc.json")
        self.assertTrue(profile["persistence"]["load_on_startup"])
        self.assertFalse(profile["matcher"]["automatic_decision_enabled"])
        self.assertIsNone(profile["matcher"]["threshold"])
        self.assertFalse(profile["recognition"]["automatic_decision_enabled"])
        self.assertIsNone(profile["recognition"]["match_threshold"])
        self.assertEqual(profile["guided_capture"]["minimum_quality_score"], 75)
        self.assertIsNone(profile["recognition"]["minimum_quality_score"])


if __name__ == "__main__":
    unittest.main()
