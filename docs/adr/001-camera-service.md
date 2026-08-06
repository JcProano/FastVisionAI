# ADR 001: Isolated Camera Service

Status: Accepted. Capture owns source connection, reconnection and `Frame`
creation. It remains independent from inference so AI failures cannot stop video.
