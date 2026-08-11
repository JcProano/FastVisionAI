"""Safe scalar-only projections for the backup window."""
from dataclasses import dataclass
from datetime import datetime
@dataclass(frozen=True,slots=True)
class BackupStatusDTO: state:str; message:str; busy:bool; unencrypted_warning:str="El backup contiene información sensible y no está cifrado."
@dataclass(frozen=True,slots=True)
class BackupOperationDTO: operation:str; success:bool; timestamp:datetime; message:str
