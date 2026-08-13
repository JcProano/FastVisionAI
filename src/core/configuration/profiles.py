from pathlib import Path
from .contracts import ConfigurationError,ConfigurationProfile
class ProfileRegistry:
 def __init__(self,mappings:dict[ConfigurationProfile,Path]):self._mappings=dict(mappings)
 @classmethod
 def development(cls,path:Path):return cls({ConfigurationProfile.DEVELOPMENT:path})
 def path_for(self,profile:ConfigurationProfile)->Path:
  try:return self._mappings[profile]
  except KeyError as exc:raise ConfigurationError("configuration profile is unavailable") from exc
