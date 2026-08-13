import inspect,unittest
from types import SimpleNamespace
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
 def _login(self,*,bootstrap=True,username="admin",password="Release123",confirmation="Release123",result=None,raises=False):
  login=LoginWindow.__new__(LoginWindow);login.bootstrap=bootstrap;login.authenticated=False;login.window=Mock();login.message=Mock();login.username=Mock();login.username.get.return_value=username;login.password=Mock();login.password.get.return_value=password;login.display_name=Mock();login.display_name.get.return_value="Administrator";login.confirmation=Mock() if bootstrap else None
  if login.confirmation:login.confirmation.get.return_value=confirmation
  login.controller=Mock();login.controller.authentication.hasher.policy.minimum_length=10;login.controller.authentication.hasher.policy.maximum_length=128
  if raises:login.controller.bootstrap.side_effect=RuntimeError("internal")
  elif bootstrap:login.controller.bootstrap.return_value=result or SimpleNamespace(success=True,message="ok")
  else:login.controller.login.return_value=result or SimpleNamespace(success=True,message="ok")
  return login
 def test_bootstrap_short_password_is_visible_and_focuses_password(self):
  login=self._login(password="Short1");login.submit();login.message.configure.assert_any_call(text="La contraseña debe tener al menos 10 caracteres.");login.password.focus_set.assert_called();login.window.destroy.assert_not_called()
 def test_bootstrap_requires_number(self):
  login=self._login(password="OnlyLetters",confirmation="OnlyLetters");login.submit();login.message.configure.assert_any_call(text="La contraseña debe contener al menos una letra y un número.")
 def test_bootstrap_requires_letter(self):
  login=self._login(password="1234567890",confirmation="1234567890");login.submit();login.message.configure.assert_any_call(text="La contraseña debe contener al menos una letra y un número.")
 def test_bootstrap_confirmation_mismatch(self):
  login=self._login(confirmation="Different1");login.submit();login.message.configure.assert_any_call(text="Las contraseñas no coinciden.");login.confirmation.focus_set.assert_called()
 def test_bootstrap_controller_error_is_safe(self):
  login=self._login(raises=True);login.submit();login.message.configure.assert_any_call(text="No se pudo crear el administrador inicial.");login.window.destroy.assert_not_called()
 def test_invalid_username_is_safe_and_focuses_username(self):
  login=self._login(username="bad user");login.submit();login.message.configure.assert_any_call(text="El usuario no es válido.");login.username.focus_set.assert_called()
 def test_normal_login_failure_is_always_generic(self):
  login=self._login(bootstrap=False,result=SimpleNamespace(success=False,message="internal unavailable"));login.submit();login.message.configure.assert_any_call(text="Credenciales inválidas.");login.window.destroy.assert_not_called()
 def test_previous_message_is_cleared_and_layout_is_visible(self):
  login=self._login(password="Short1");login.submit();self.assertEqual(login.message.configure.call_args_list[0].kwargs,{"text":""});login.window.update_idletasks.assert_called()
  source=inspect.getsource(LoginWindow.__init__);self.assertIn("wraplength=360",source);self.assertIn("pady=(12,8)",source)
