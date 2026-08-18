import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.core.configuration import ConfigurationProfile, ConfigurationValidator
from src.core.security import AuthorizationPermission, UserRole
from src.ui.main import (StartupMode, appliance_mode_enabled, apply_startup_mode,
                         build_security, configured_startup_mode,
                         start_appliance_admin_session)


class JetsonApplianceTests(unittest.TestCase):
    def test_startup_modes_are_explicit_and_compose_tk_web(self):
        base={"ui":{"startup_mode":"ASK","tk_enabled":True},
              "web_dashboard":{"enabled":True,"open_browser_on_start":True}}
        self.assertIs(configured_startup_mode(base),StartupMode.ASK)
        tk=apply_startup_mode(base,StartupMode.TK)
        self.assertTrue(tk["ui"]["tk_enabled"]);self.assertFalse(tk["web_dashboard"]["enabled"])
        self.assertFalse(tk["web_dashboard"]["open_browser_on_start"])
        web=apply_startup_mode(base,StartupMode.WEB)
        self.assertFalse(web["ui"]["tk_enabled"]);self.assertTrue(web["web_dashboard"]["enabled"])
        both=apply_startup_mode(base,StartupMode.BOTH)
        self.assertTrue(both["ui"]["tk_enabled"]);self.assertTrue(both["web_dashboard"]["enabled"])

    def test_legacy_startup_configuration_remains_supported(self):
        self.assertIs(configured_startup_mode({"ui":{"tk_enabled":True},"web_dashboard":{"enabled":False}}),StartupMode.TK)
        self.assertIs(configured_startup_mode({"ui":{"tk_enabled":False},"web_dashboard":{"enabled":True}}),StartupMode.WEB)

    def test_jetson_asks_and_registered_popup_lasts_sixty_seconds(self):
        settings=json.loads(Path("config/local_face_validation.jetson.json").read_text())
        self.assertEqual(settings["ui"]["startup_mode"],"ASK")
        self.assertEqual(settings["identification_popup"]["registered_popup_timeout_seconds"],60)

    def test_appliance_session_is_ephemeral_admin_and_does_not_touch_users_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);settings={"security":{"enabled":True,"appliance_mode":True,"database_path":"data/users.db"}}
            security=build_security(settings,root)
            database=root/"data/users.db"
            self.assertFalse(database.exists())
            session=start_appliance_admin_session(security)
            self.assertEqual(session.role,UserRole.ADMIN)
            self.assertTrue(security.authorization.can(AuthorizationPermission.VIEW_DASHBOARD))
            self.assertFalse(database.exists())
            security.logout();self.assertIsNone(security.sessions.current());self.assertFalse(database.exists())

    def test_appliance_false_keeps_persistent_login_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);security=build_security({"security":{"enabled":True,"appliance_mode":False,"database_path":"data/users.db"}},root)
            self.assertTrue((root/"data/users.db").exists());self.assertIsNone(security.sessions.current())

    def test_mode_is_explicit_boolean_and_not_local_validation_bypass(self):
        self.assertTrue(appliance_mode_enabled({"security":{"enabled":True,"appliance_mode":True,"skip_login_for_local_validation":False}}))
        self.assertFalse(appliance_mode_enabled({"security":{"enabled":True,"skip_login_for_local_validation":True}}))
        with self.assertRaises(ValueError):appliance_mode_enabled({"security":{"enabled":True,"appliance_mode":"true"}})

    def test_jetson_profile_is_valid_and_biometrics_equal_production(self):
        root=Path(__file__).resolve().parents[1]
        production=json.loads((root/"config/local_face_validation.prod.json").read_text())
        jetson=json.loads((root/"config/local_face_validation.jetson.json").read_text())
        result=ConfigurationValidator(root).validate(jetson,ConfigurationProfile.PRODUCTION)
        self.assertTrue(result.valid,tuple((item.path,item.message) for item in result.issues))
        for section in ("matcher","recognition","guided_capture","quality","enrollment","stability","identification_policy","decision_orchestrator","action_executor"):
            self.assertEqual(jetson[section],production[section],section)
        self.assertTrue(jetson["security"]["appliance_mode"]);self.assertFalse(production["security"]["appliance_mode"])

    def test_web_validation_host_port_limits_and_experimental_no_tk(self):
        root=Path(__file__).resolve().parents[1];validator=ConfigurationValidator(root)
        base={"web_dashboard":{"enabled":True,"host":"127.0.0.1","port":8080,"video_max_fps":10,"video_jpeg_quality":75,"max_stream_clients":3},"ui":{"tk_enabled":True}}
        self.assertTrue(validator.validate(base,ConfigurationProfile.DEVELOPMENT).valid)
        for field,value in (("host","http://bad"),("port",70000),("video_max_fps",31),("video_jpeg_quality",0),("max_stream_clients",11)):
            candidate=json.loads(json.dumps(base));candidate["web_dashboard"][field]=value
            self.assertFalse(validator.validate(candidate,ConfigurationProfile.DEVELOPMENT).valid,field)
        self.assertFalse(validator.validate({"web_dashboard":{"enabled":False},"ui":{"tk_enabled":False}},ConfigurationProfile.DEVELOPMENT).valid)


if __name__=="__main__":unittest.main()
