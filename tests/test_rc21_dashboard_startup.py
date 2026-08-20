import inspect
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.ui.main import main
from src.ui.tk_app import LocalFaceTkApp


class FakeClipboardRoot:
    def __init__(self):self.value=None
    def clipboard_clear(self):self.value=None
    def clipboard_append(self,value):self.value=value
    def update_idletasks(self):pass


class RC21DashboardStartupTests(unittest.TestCase):
    def app(self,local="http://127.0.0.1:8080",lan=None):
        app=LocalFaceTkApp.__new__(LocalFaceTkApp)
        app.root=FakeClipboardRoot();app._web_dashboard_local_url=local
        app._web_dashboard_lan_url=lan;app._browser_open=Mock(return_value=True)
        return app

    def test_startup_never_schedules_camera_administration(self):
        source=inspect.getsource(main)
        self.assertNotIn("root.after(0, open_camera_selection)",source)
        self.assertIn("session.start()",source)

    def test_camera_button_remains_operator_wired(self):
        source=inspect.getsource(LocalFaceTkApp.__init__)
        self.assertIn('("◉","Cámara",on_camera,True)',source)
        self.assertIn('self.camera_button=self.sidebar_buttons["Cámara"]',source)

    def test_web_url_prefers_lan_for_copy_and_localhost_for_open(self):
        app=self.app(lan="http://192.168.1.50:8080")
        self.assertTrue(app.copy_web_dashboard_url())
        self.assertEqual(app.root.value,"http://192.168.1.50:8080")
        self.assertTrue(app.open_web_dashboard())
        app._browser_open.assert_called_once_with("http://127.0.0.1:8080")

    def test_web_url_falls_back_to_localhost(self):
        app=self.app()
        self.assertEqual(app.selected_web_dashboard_url(),"http://127.0.0.1:8080")
        self.assertTrue(app.copy_web_dashboard_url())

    def test_logo_path_is_project_relative_and_has_safe_fallback(self):
        source=inspect.getsource(LocalFaceTkApp.__init__)
        self.assertIn('Path(__file__).resolve().parent/"assets"',source)
        self.assertIn('text="ISTSB"',source)
        self.assertTrue((Path("src/ui/assets")/"README.md").is_file())


if __name__=="__main__":unittest.main()
