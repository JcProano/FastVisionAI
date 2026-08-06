# ADR 002: Bounded Frame Queue

Status: Accepted. Realtime sources discard the oldest frame; video files wait.
Bounded memory and cancellation take precedence over processing every live frame.
