from __future__ import annotations

import inspect
import tempfile
import unittest
import uuid
from pathlib import Path

from src.camera.source_discovery import (
    CameraSelectionController,CameraSourceDiscovery,CameraSourceType,parse_discovery_config,
)
from src.core.person_database import PersonCreateRequest,PersonRepository,PersonStatus
from src.engine.enrollment import EnrollmentPolicy,EnrollmentService
from src.engine.gallery import FaceGallery,FaceIdentity
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.camera_selection_window import CameraSelectionWindow
from src.ui.main import main
from src.ui.people.controller import PeopleManagerController
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.people.tk_window import PeopleManagerWindow
from src.ui.web_dashboard.controller import WebDashboardController
from tests.test_face_gallery import GalleryTestCase


class RC213SafeAdministrationTests(GalleryTestCase):
    def camera_controller(self):
        config=parse_discovery_config({"source":"auto","auto_discovery":True,
            "preferred_source":"net-1","network_sources":[
                {"id":"net-1","type":"NETWORK_HTTP","name":"Casa",
                 "url":"http://user:secret@camera/video"}]})
        persisted=[]
        discovery=CameraSourceDiscovery(config,path_exists=lambda _path:False)
        controller=CameraSelectionController(
            discovery,persist_config=lambda value:persisted.append(value) or True,
        )
        controller.refresh()
        return controller,persisted

    def test_camera_edit_and_delete_use_configuration_boundary(self):
        controller,persisted=self.camera_controller()
        controller.update_network_source(
            "net-1","Entrada",CameraSourceType.NETWORK_RTSP,
            "rtsp://admin:password@camera/live",preferred=False,
        )
        edited=persisted[-1]
        self.assertEqual((edited.network_sources[0].name,edited.network_sources[0].source_type),
                         ("Entrada",CameraSourceType.NETWORK_RTSP))
        self.assertIsNone(edited.preferred_source)
        self.assertNotIn("password",repr(controller.refresh().sources))
        controller.remove_network_source("net-1")
        self.assertEqual(persisted[-1].network_sources,())

    def test_local_camera_cannot_be_edited_or_deleted(self):
        controller,_=self.camera_controller()
        with self.assertRaises(ValueError):
            controller.update_network_source(
                "v4l2:0","Local",CameraSourceType.LOCAL_V4L2,"0",preferred=False,
            )
        with self.assertRaises(ValueError):controller.remove_network_source("v4l2:0")

    def test_camera_ui_has_row_actions_confirmation_and_no_silent_fallback(self):
        source=inspect.getsource(CameraSelectionWindow)
        for label in ("USAR","PROBAR","EDITAR","ELIMINAR","CÁMARA PRINCIPAL"):
            self.assertIn(label,source)
        startup=inspect.getsource(main)
        block=startup[startup.index("def delete_camera"):startup.index("def open_camera_selection")]
        self.assertIn("ReconnectConfig(enabled=False)",block)
        self.assertIn('current_camera_source["id"]=None',block)
        self.assertNotIn("finish_startup_camera_discovery",block)

    def test_person_civil_edit_preserves_templates_and_delete_is_coordinated(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);gallery=FaceGallery();person_id=str(uuid.uuid4())
            gallery.register_identity(FaceIdentity(person_id,"Ana Pérez",{}))
            gallery.add_template(person_id,self.embedding([1,0,0]))
            biometrics=PeopleManagerController(
                gallery,EnrollmentService(gallery,EnrollmentPolicy(1,5)),
                GalleryPersistence(enabled=True),root/"gallery.json",root/"gallery.npz",
            )
            self.assertTrue(biometrics.save_changes().success)
            repository=PersonRepository(root/"people.db");repository.initialize()
            repository.create(PersonCreateRequest(
                person_id,"1710034065","Ana","Pérez",email="old@example.test",
            ));repository.set_status(person_id,PersonStatus.ACTIVE)
            deleted=[]
            thumbnails=type("Thumbs",(),{"delete":lambda _self,value:deleted.append(value) or True})()
            controller=DatabasePeopleManagerController(
                repository,biometrics,thumbnail_manager=thumbnails,
            )
            before=tuple(gallery.templates())
            edited=controller.update_person(
                person_id,"Ana María","Pérez",None,email="new@example.test",
            )
            self.assertTrue(edited.success);self.assertEqual(tuple(gallery.templates()),before)
            removed=controller.delete_person(person_id,confirmed=True)
            self.assertTrue(removed.success)
            self.assertEqual((len(gallery.list_identities()),len(gallery.templates())),(0,0))
            self.assertEqual(deleted,[person_id])
            self.assertEqual(repository.get_by_person_id(person_id).status,PersonStatus.DISABLED)
            imported=FaceGallery();GalleryPersistence(enabled=True).import_into(
                imported,root/"gallery.json",root/"gallery.npz",
            )
            self.assertEqual((len(imported.list_identities()),len(imported.templates())),(0,0))

    def test_face_replacement_replaces_instead_of_appending(self):
        gallery=FaceGallery();gallery.register_identity(FaceIdentity("p1","Ada",{}))
        gallery.add_template("p1",self.embedding([1,0,0]))
        manager=PeopleManagerController(
            gallery,EnrollmentService(gallery,EnrollmentPolicy(1,5)),
            GalleryPersistence(enabled=True),Path("unused.json"),Path("unused.npz"),
        )
        self.assertTrue(manager.begin_replacement("p1").success)
        result=manager.complete_additional("p1",((self.embedding([0,1,0],index=1),None),))
        self.assertTrue(result.success);self.assertEqual(len(gallery.templates("p1")),1)
        self.assertAlmostEqual(float(gallery.templates("p1")[0].template.embedding[1]),1.0)

    def test_web_person_commands_use_opaque_token_and_strong_confirmation(self):
        calls=[];controller=WebDashboardController(lambda:None,actions={
            "person_delete":lambda person_id,confirmed:calls.append((person_id,confirmed)),
        })
        token=controller._person_token("safe-person")
        with self.assertRaises(ValueError):
            controller.action("/api/person/delete",{"token":token,"confirmed":True})
        controller.action("/api/person/delete",{
            "token":token,"confirmed":True,"confirmation":"ELIMINAR",
        })
        self.assertEqual(calls,[("safe-person",True)])
        page=inspect.getsource(WebDashboardController._people_page)
        for label in ("VER","EDITAR","ELIMINAR","ACTUALIZAR FOTO","ACTUALIZAR ROSTRO"):
            self.assertIn(label,page)

    def test_tk_person_confirmation_and_separate_photo_face_actions(self):
        source=inspect.getsource(PeopleManagerWindow)
        self.assertIn("ELIMINAR DEFINITIVAMENTE",source)
        self.assertIn("ACTUALIZAR FOTO",source)
        self.assertIn("ACTUALIZAR ROSTRO",source)


if __name__ == "__main__":unittest.main()
