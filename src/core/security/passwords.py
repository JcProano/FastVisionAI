from __future__ import annotations
import hashlib, json, secrets
from .contracts import PasswordHashDTO, PasswordPolicy, SecurityError

class PasswordHasher:
    ALGORITHM="scrypt"; VERSION=1
    def __init__(self, policy: PasswordPolicy|None=None, *, n=16384, r=8, p=1, dklen=64, salt_bytes=32):
        if n < 2 or n & (n-1) or min(r,p,dklen,salt_bytes)<=0: raise ValueError("scrypt parameters invalid")
        self.policy=policy or PasswordPolicy(); self.parameters={"version":1,"n":n,"r":r,"p":p,"dklen":dklen}
        self.salt_bytes=salt_bytes
    def hash_password(self,password:str)->PasswordHashDTO:
        self.policy.validate(password); salt=secrets.token_bytes(self.salt_bytes)
        digest=self._derive(password,salt,self.parameters)
        return PasswordHashDTO(digest,salt,self.ALGORITHM,json.dumps(self.parameters,sort_keys=True,separators=(",",":")))
    def verify_password(self,password:str,stored:PasswordHashDTO)->bool:
        if stored.algorithm != self.ALGORITHM: return False
        try: params=json.loads(stored.parameters)
        except Exception: return False
        if params != self.parameters or params.get("version") != self.VERSION: return False
        try: candidate=self._derive(password,stored.password_salt,params)
        except Exception: return False
        return secrets.compare_digest(candidate,stored.password_hash)
    @staticmethod
    def _derive(password,salt,params):
        return hashlib.scrypt(password.encode("utf-8"),salt=salt,n=params["n"],r=params["r"],p=params["p"],dklen=params["dklen"])
