import inspect
import unittest

from src.camera.source_discovery import CameraSourceDTO, CameraSourceType, redact_url
from src.ui.camera_selection_window import CameraSelectionWindow, NetworkCameraDialog


class Var:
    def __init__(self, value=""): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class Controller:
    def __init__(self): self.added=[];self.updated=[];self.probed=[]
    def probe_network_source_details(self,name,kind,url):
        self.probed.append((name,kind,url));return True,(1280,720)
    def add_network_source(self,name,kind,url):
        self.added.append((name,kind,url))
        return CameraSourceDTO("network-new",kind,name,False,False,
                               {"endpoint":redact_url(url)})
    def update_network_source(self,source_id,name,kind,url,*,preferred):
        self.updated.append((source_id,name,kind,url,preferred))
        return CameraSourceDTO(source_id,kind,name,False,preferred,
                               {"endpoint":redact_url(url)})


def dialog(controller, *, source=None):
    value=NetworkCameraDialog.__new__(NetworkCameraDialog)
    value.controller=controller;value.source=source;value.on_saved=lambda item:value.saved.append(item)
    value.saved=[];value.cancel=lambda:None
    value.name=Var("iPhone local");value.profile=Var("DroidCam")
    value.connection_type=Var("HTTP/MJPEG");value.host=Var("");value.port=Var("")
    value.path=Var("");value.username=Var("");value.password=Var("")
    value.full_url=Var("http://192.168.1.12:4747/video")
    value.preview=Var();value.result=Var()
    return value


class RC228CameraModalTests(unittest.TestCase):
    def test_add_and_edit_open_the_same_separate_modal(self):
        selector=inspect.getsource(CameraSelectionWindow)
        modal=inspect.getsource(NetworkCameraDialog.__init__)
        self.assertIn("self._open_network_dialog(None)",selector)
        self.assertIn("self._open_network_dialog(source)",selector)
        self.assertNotIn("self.network_form =",selector)
        for required in ("tk.Toplevel(parent)","600x500","transient(parent)","grab_set()"):
            self.assertIn(required,modal)

    def test_modal_contains_required_fields_and_actions(self):
        source=inspect.getsource(NetworkCameraDialog.__init__)
        for label in ("Nombre de cámara *","Fabricante / Perfil","Tipo de conexión *",
                      "Host / IP *","Puerto","Ruta / Stream","Usuario","Contraseña",
                      "URL final / Vista previa","PROBAR CONEXIÓN","CANCELAR",
                      "GUARDAR CÁMARA","GUARDAR CAMBIOS"):
            self.assertIn(label,source)

    def test_simple_url_probe_does_not_save_or_change_active_camera(self):
        controller=Controller();value=dialog(controller)
        value.test_connection()
        self.assertEqual(controller.added,[]);self.assertEqual(controller.updated,[])
        self.assertEqual(len(controller.probed),1)
        self.assertIn("CONECTADA",value.result.get());self.assertIn("1280×720",value.result.get())

    def test_save_creates_refreshes_and_selects_without_connecting(self):
        controller=Controller();value=dialog(controller)
        value.save()
        self.assertEqual(len(controller.added),1);self.assertEqual(len(value.saved),1)
        self.assertEqual(value.saved[0].source_id,"network-new")
        selector=inspect.getsource(CameraSelectionWindow._network_saved)
        self.assertIn("self.refresh()",selector)
        self.assertIn("self.selected_source_id.set(source.source_id)",selector)
        self.assertNotIn("on_use",selector)

    def test_edit_uses_same_modal_path_and_persists_changes(self):
        source=CameraSourceDTO("network-old",CameraSourceType.NETWORK_HTTP,
                               "Anterior",False,True,{"endpoint":"http://camera/video"})
        controller=Controller();value=dialog(controller,source=source)
        value.name.set("Nueva");value.save()
        self.assertEqual(controller.updated[0][0],"network-old")
        self.assertEqual(controller.updated[0][1],"Nueva")
        self.assertTrue(controller.updated[0][-1])

    def test_edit_preloads_saved_endpoint_into_the_shared_fields(self):
        source=inspect.getsource(NetworkCameraDialog._load)
        for assignment in ("self.name.set(configured.name)",
                           "self.host.set(parsed.hostname or",
                           "self.port.set(","self.path.set(",
                           "self.username.set(parsed.username or",
                           "self.password.set(parsed.password or"):
            self.assertIn(assignment,source)

    def test_password_is_masked_and_preview_is_redacted(self):
        controller=Controller();value=dialog(controller)
        value.full_url.set("");value.connection_type.set("RTSP")
        value.host.set("camera.local");value.username.set("operator")
        value.password.set("supersecret");value.path.set("stream")
        value._update_preview()
        self.assertNotIn("supersecret",value.preview.get())
        self.assertNotIn("operator",value.preview.get())
        self.assertIn("***",value.preview.get())
        self.assertIn('show="*" if variable is self.password',
                      inspect.getsource(NetworkCameraDialog.__init__))

    def test_cancel_has_no_configuration_side_effect(self):
        controller=Controller();value=dialog(controller)
        value.cancel()
        self.assertEqual((controller.added,controller.updated,controller.probed),([],[],[]))


if __name__ == "__main__": unittest.main()
