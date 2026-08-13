"""Legacy callback adapter; intentionally not connected to ApplicationEventBus."""
from __future__ import annotations
from collections.abc import Callable
from .contracts import AuditAction,AuditEntityType

class AuditCallbackAdapter:
    def __init__(self,service,context:Callable[[],object],source:str,entity_type:AuditEntityType|None=None):self.service=service;self.context=context;self.source=source;self.entity_type=entity_type
    def __call__(self,event:str,payload:dict[str,str])->None:
        try:action=AuditAction(event)
        except ValueError:return
        context=self.context()
        actor=(payload.get("user_id") if event=="LOGOUT" else getattr(context,"user_id",None))
        role=payload.get("actor_role") or getattr(context,"role",None);session=payload.get("session_id") or getattr(context,"session_id",None)
        if hasattr(role,"value"):role=role.value
        entity_id=payload.get("user_id") or payload.get("person_id") or payload.get("entity_id")
        safe={key:value for key,value in payload.items() if key not in {"user_id","person_id","entity_id","actor_role","session_id"}}
        self.service.safe_record(action,self.entity_type or _entity(action),actor_user_id=actor,actor_role=role,entity_id=entity_id,success=not event.endswith("FAILED") and event not in {"LOGIN_FAILURE","CONFIG_IMPORT_REJECTED"},message=event.replace("_"," ").title(),source=self.source,session_id=session,metadata=safe)

def _entity(action:AuditAction)->AuditEntityType:
    prefix=action.value.split("_",1)[0]
    return {"LOGIN":AuditEntityType.SESSION,"LOGOUT":AuditEntityType.SESSION,"PASSWORD":AuditEntityType.USER,"USER":AuditEntityType.USER,"PERSON":AuditEntityType.PERSON,"MANUAL":AuditEntityType.ATTENDANCE,"REPORT":AuditEntityType.REPORT,"CONFIG":AuditEntityType.CONFIGURATION,"BACKUP":AuditEntityType.BACKUP,"VERIFY":AuditEntityType.BACKUP,"RESTORE":AuditEntityType.BACKUP,"SYSTEM":AuditEntityType.SYSTEM_HEALTH}[prefix]
