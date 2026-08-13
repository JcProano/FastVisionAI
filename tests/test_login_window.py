import inspect,unittest
from unittest.mock import Mock
from src.ui.security.login_window import LoginWindow
class LoginWindowTests(unittest.TestCase):
 def test_password_is_masked_and_camera_is_unknown(self):
  source=inspect.getsource(LoginWindow);self.assertIn('show="•"',source);self.assertNotIn("CameraManager",source);self.assertNotIn("password_hash",source)
 def test_withdrawn_root_does_not_become_transient_parent(self):
  login=LoginWindow.__new__(LoginWindow);login.root=Mock();login.root.state.return_value="withdrawn";login.root.winfo_viewable.return_value=0;login.window=Mock();login.username=Mock();login.window.winfo_reqwidth.return_value=250;login.window.winfo_reqheight.return_value=180;login.window.winfo_screenwidth.return_value=1200;login.window.winfo_screenheight.return_value=800
  login._prepare_window()
  login.window.transient.assert_not_called();login.window.update_idletasks.assert_called_once();login.window.minsize.assert_called_once_with(420,280);login.window.geometry.assert_called_once_with("420x280+390+260");login.window.deiconify.assert_called_once();login.window.lift.assert_called_once();login.window.focus_force.assert_called_once();login.window.grab_set.assert_called_once();login.username.focus_set.assert_called_once()
 def test_visible_root_can_be_transient_parent(self):
  login=LoginWindow.__new__(LoginWindow);login.root=Mock();login.root.state.return_value="normal";login.root.winfo_viewable.return_value=1;login.window=Mock();login.username=Mock();login.window.winfo_reqwidth.return_value=420;login.window.winfo_reqheight.return_value=280;login.window.winfo_screenwidth.return_value=1200;login.window.winfo_screenheight.return_value=800
  login._prepare_window();login.window.transient.assert_called_once_with(login.root)
