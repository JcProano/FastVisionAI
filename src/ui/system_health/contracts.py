from dataclasses import dataclass
@dataclass(frozen=True,slots=True)
class SystemHealthPresentationDTO:overall:str;components:tuple[tuple[str,str,str,str],...];fps:str;frame_interval:str;processing_latency:str;inference_latency:str;queue_depth:str;dropped_frames:str;memory:str;uptime:str
