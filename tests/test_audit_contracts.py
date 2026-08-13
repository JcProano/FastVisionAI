from __future__ import annotations
import unittest
from dataclasses import fields
from datetime import datetime,timezone
from src.core.audit import AuditAction,AuditEntityType,AuditQuery,AuditRecordDTO,AuditValidationError

class AuditContractTests(unittest.TestCase):
 def test_actions_are_explicit(self):
  self.assertIn(AuditAction.PERSON_CREATED,tuple(AuditAction));self.assertIn(AuditAction.RESTORE_FAILED,tuple(AuditAction))
 def test_invalid_pagination(self):
  with self.assertRaises(AuditValidationError):AuditQuery(limit=0)
 def test_public_dto_has_no_biometric_or_secret_fields(self):
  names={item.name.casefold() for item in fields(AuditRecordDTO)}
  self.assertTrue(names.isdisjoint({"embedding","template","image","password","hash","salt","metadata"}))
 def test_invalid_dates(self):
  now=datetime.now(timezone.utc)
  with self.assertRaises(AuditValidationError):AuditQuery(date_from=now,date_to=datetime(2000,1,1,tzinfo=timezone.utc))

