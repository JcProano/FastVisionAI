from __future__ import annotations

import inspect
import unittest

from src.camera.source_discovery import CameraSourceDTO,CameraSourceType
from src.ui.camera_selection_window import CameraSelectionWindow


class Var:
    def __init__(self,value=""):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


class Widget:
    def __init__(self):self.values={}
    def configure(self,**values):self.values.update(values)


def source(source_id="network-7b4e8bd7-9163-434d-bd62-a47c22b799c9",
           *,available=True):
    return CameraSourceDTO(
        source_id,CameraSourceType.NETWORK_HTTP,"Iphone local",available,False,
        {"transport":"HTTP/MJPEG","endpoint":"http://192.168.1.12:4747/video"},
    )


class Controller:
    def __init__(self,item,*,probe=True):
        self.sources=(item,);self.probe_result=probe;self.used=[];self.probed=[]
    def probe(self,source_id):
        self.probed.append(source_id)
        if self.probe_result:self.sources=(source(source_id,available=True),)
        return self.probe_result
    def use(self,source_id):
        self.used.append(source_id)
        return next(item for item in self.sources
                    if item.source_id==source_id and item.available)
    def set_preferred(self,_source_id):pass


def window(controller,selected_id):
    value=CameraSelectionWindow.__new__(CameraSelectionWindow)
    value.controller=controller
    value.selected_source_id=Var(selected_id);value.selected=value.selected_source_id
    value.preferred=Var(False);value.status=Widget();value._selected_was_available=False
    value.current_source_id=lambda:None
    value.on_use=lambda _source:True
    value.close=lambda:None
    value.refresh=lambda:None
    return value


class RC224CameraSelectorRegressionTests(unittest.TestCase):
    def test_selection_uses_and_preserves_real_iphone_source_id(self):
        item=source();controller=Controller(item);chooser=window(controller,"")
        chooser.selected_source_id.set(item.source_id)
        chooser._selection_changed()
        self.assertEqual(chooser.selected_source_id.get(),item.source_id)
        self.assertEqual(chooser.status.values.get("text"),"")

    def test_use_selected_passes_exact_source_id(self):
        item=source();controller=Controller(item);chooser=window(controller,item.source_id)
        CameraSelectionWindow.use_selected(chooser)
        self.assertEqual(controller.used,[item.source_id])

    def test_probe_keeps_selection_and_refreshes_availability(self):
        item=source(available=False);controller=Controller(item,probe=True)
        chooser=window(controller,item.source_id)
        CameraSelectionWindow.test_selected(chooser)
        self.assertEqual(chooser.selected_source_id.get(),item.source_id)
        self.assertEqual(controller.probed,[item.source_id])
        self.assertIn("disponible",chooser.status.values["text"].casefold())

    def test_offline_use_keeps_selection_and_reports_specific_error(self):
        item=source(available=False);controller=Controller(item,probe=False)
        chooser=window(controller,item.source_id)
        CameraSelectionWindow.use_selected(chooser)
        self.assertEqual(chooser.selected_source_id.get(),item.source_id)
        self.assertEqual(controller.used,[])
        self.assertIn("offline",chooser.status.values["text"].casefold())
        self.assertNotIn("ya no está disponible",chooser.status.values["text"].casefold())

    def test_ui_has_one_final_use_action_and_truthful_availability(self):
        source_text=inspect.getsource(CameraSelectionWindow)
        render=inspect.getsource(CameraSelectionWindow._render_group)
        self.assertEqual(source_text.count('text="USAR ESTA CÁMARA"'),1)
        self.assertNotIn('text="USAR"',render)
        self.assertIn('"DISPONIBLE" if source.available else "OFFLINE"',render)
        self.assertIn("value=source.source_id",render)

    def test_refresh_and_selection_rules_are_explicit(self):
        refresh=inspect.getsource(CameraSelectionWindow.refresh)
        selection=inspect.getsource(CameraSelectionWindow._selection_changed)
        self.assertIn("previous_id",refresh)
        self.assertIn("existing is not None",refresh)
        self.assertIn("previous_was_available",refresh)
        self.assertIn('self.status.configure(text="")',selection)


if __name__ == "__main__":unittest.main()
