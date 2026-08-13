import dataclasses,unittest
from datetime import datetime,timezone
from src.core.system_health import *
class ContractsTests(unittest.TestCase):
 def test_levels_and_all_disabled(self):
  now=datetime.now(timezone.utc);items=tuple(ComponentHealthDTO(str(i),HealthLevel.DISABLED,"off",now) for i in range(2));self.assertEqual(overall_level(items),HealthLevel.UNKNOWN)
 def test_precedence(self):
  now=datetime.now(timezone.utc)
  for levels,expected in (((HealthLevel.OK,),HealthLevel.OK),((HealthLevel.OK,HealthLevel.UNKNOWN),HealthLevel.UNKNOWN),((HealthLevel.WARNING,HealthLevel.UNKNOWN),HealthLevel.WARNING),((HealthLevel.ERROR,HealthLevel.WARNING),HealthLevel.ERROR)):
   self.assertEqual(overall_level(tuple(ComponentHealthDTO(str(i),x,"safe",now) for i,x in enumerate(levels))),expected)
 def test_dtos_have_no_sensitive_fields(self):
  forbidden={"path","frame","image","embedding","template","array","username","token","model","repository","exception"}
  for cls in (ComponentHealthDTO,SystemHealthDTO,PerformanceMetricsDTO):self.assertFalse({f.name for f in dataclasses.fields(cls)}&forbidden)
