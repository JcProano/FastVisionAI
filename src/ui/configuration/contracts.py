from dataclasses import dataclass
@dataclass(frozen=True,slots=True)
class ConfigurationUIStateDTO:legacy_configuration:bool;profile:str;restart_required_pending:bool;editable:bool;message:str
