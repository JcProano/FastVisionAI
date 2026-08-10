import dataclasses,unittest,uuid
import numpy as np
from src.core.security import *
from src.ui.security.contracts import *
class SecurityContractTests(unittest.TestCase):
 def test_public_contracts_have_no_secrets_or_biometrics(self):
  for cls in (UserDTO,AuthenticationResult,AuthenticatedSessionDTO,AuthorizationResult,UserOperationResult,LoginResultDTO,UserSummaryDTO,SecurityStatusDTO):
   names={f.name for f in dataclasses.fields(cls)}
   self.assertFalse(names & {"password","password_hash","password_salt","password_parameters","embedding","image"});self.assertNotIn(np.ndarray,{f.type for f in dataclasses.fields(cls)})
 def test_ids_and_usernames_are_canonical(self):
  value=str(uuid.uuid4());request=UserCreateRequest(value," Admin.User "," Admin User ",UserRole.ADMIN);self.assertEqual(request.username,"admin.user");self.assertEqual(request.user_id,value)
