from __future__ import annotations
import tempfile,unittest,uuid
from pathlib import Path
from src.core.audit import AuditRepository
from src.core.person_database import PersonRepository
from src.core.security import AuthenticationRequest,AuthenticationService,PasswordHasher,UserCreateRequest,UserRepository,UserRole

class StartupSmokeTests(unittest.TestCase):
 def test_temporary_repositories_and_security_bootstrap(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name);people=PersonRepository(root/"people.db");audit=AuditRepository(root/"audit.db");users=UserRepository(root/"users.db");self.assertEqual(people.initialize(),1);self.assertEqual(audit.initialize(),1);users.initialize();auth=AuthenticationService(users,PasswordHasher());result=auth.bootstrap_admin(UserCreateRequest(str(uuid.uuid4()),"admin.rc","RC Admin",UserRole.ADMIN),"Release12345");self.assertTrue(result.success);self.assertTrue(auth.authenticate(AuthenticationRequest("admin.rc","Release12345")).success)
 def test_main_orders_login_before_real_adapter(self):
  source=(Path(__file__).resolve().parents[2]/"src/ui/main.py").read_text();self.assertLess(source.index("if not authenticate_startup("),source.index("adapter = RealUIRuntimeAdapter"))
