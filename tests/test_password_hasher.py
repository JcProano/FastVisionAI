import unittest
from src.core.security import PasswordHashDTO,PasswordHasher,PasswordPolicy,SecurityValidationError
class PasswordHasherTests(unittest.TestCase):
 def setUp(self):self.hasher=PasswordHasher()
 def test_scrypt_hash_and_verify(self):
  first=self.hasher.hash_password("SecurePass1");second=self.hasher.hash_password("SecurePass1")
  self.assertEqual(first.algorithm,"scrypt");self.assertNotEqual(first.password_salt,second.password_salt);self.assertNotEqual(first.password_hash,b"SecurePass1");self.assertTrue(self.hasher.verify_password("SecurePass1",first));self.assertFalse(self.hasher.verify_password("WrongPass1",first))
 def test_unknown_version_fails_safe(self):
  valid=self.hasher.hash_password("SecurePass1");bad=PasswordHashDTO(valid.password_hash,valid.password_salt,"unknown",valid.parameters);self.assertFalse(self.hasher.verify_password("SecurePass1",bad))
 def test_policy_bounds(self):
  with self.assertRaises(SecurityValidationError):PasswordPolicy().validate("short1")
  with self.assertRaises(SecurityValidationError):PasswordPolicy().validate("x"*129+"1")
