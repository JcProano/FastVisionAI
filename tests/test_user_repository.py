import sqlite3,unittest,uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.security import *
from src.core.security.migrations import SecurityMigrationError
class UserRepositoryTests(unittest.TestCase):
 def setUp(self):self.temp=TemporaryDirectory();self.repo=UserRepository(Path(self.temp.name)/"users.db");self.assertEqual(self.repo.initialize(),1);self.hasher=PasswordHasher()
 def tearDown(self):self.temp.cleanup()
 def create(self,name="admin",role=UserRole.ADMIN):return self.repo.create_user(UserCreateRequest(str(uuid.uuid4()),name,name.title(),role),self.hasher.hash_password("SecurePass1"))
 def test_create_get_list_update_status(self):
  admin=self.create();self.assertEqual(self.repo.count_users(),1);self.assertEqual(self.repo.get_by_username("ADMIN").user_id,admin.user_id);self.assertEqual(len(self.repo.list_users()),1);self.assertEqual(self.repo.update_user(UserUpdateRequest(admin.user_id,"New Name")).display_name,"New Name")
 def test_duplicate_case_insensitive(self):
  self.create("admin")
  with self.assertRaises(DuplicateUsernameError):self.create("ADMIN",UserRole.VIEWER)
 def test_last_admin_transactional_protection(self):
  admin=self.create()
  with self.assertRaises(LastActiveAdminError):self.repo.set_status(admin.user_id,UserStatus.DISABLED)
  self.assertEqual(self.repo.get_by_user_id(admin.user_id).status,UserStatus.ACTIVE)
 def test_future_schema_rejected(self):
  with sqlite3.connect(self.repo.path) as c:c.execute("INSERT INTO schema_version VALUES(2,'now')")
  with self.assertRaises(SecurityMigrationError):self.repo.initialize()
