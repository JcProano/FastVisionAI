"""Biometric-free UI projections for operator security."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from src.core.security import UserRole, UserStatus

class SecurityUIState(str,Enum): LOGIN="LOGIN"; BOOTSTRAP="BOOTSTRAP"; AUTHENTICATED="AUTHENTICATED"; TIMEOUT_PENDING="TIMEOUT_PENDING"; LOGGED_OUT="LOGGED_OUT"; ERROR="ERROR"
@dataclass(frozen=True,slots=True)
class LoginResultDTO: success:bool; message:str; state:SecurityUIState; display_name:str|None=None; role:str|None=None
@dataclass(frozen=True,slots=True)
class UserSummaryDTO: user_id:str; username:str; display_name:str; role:str; status:str; last_login_at:str|None
@dataclass(frozen=True,slots=True)
class SecurityStatusDTO: enabled:bool; authenticated:bool; state:SecurityUIState; operator_display_name:str|None; role:str|None; timeout_pending:bool=False
