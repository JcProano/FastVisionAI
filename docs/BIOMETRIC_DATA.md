# Biometric data handling

Face embeddings are sensitive biometric data. They must not be written to
application logs, exception messages, diagnostics or console output. Temporary
identifiers used by validation tools are not real identities.

`FaceGallery` is an in-memory development implementation. Optional JSON+NPZ
export is explicit and disabled by default. JSON stores metadata and NPZ stores
the numeric templates; this format provides integrity validation but **does not
provide encryption** and is not suitable for production storage.

A production persistence layer must include encryption at rest and in transit,
least-privilege access control, audit trails, explicit retention limits,
verifiable deletion and external key management with rotation. Legal basis,
consent, data minimization and incident response must be defined for the target
jurisdiction before collecting real identities.

Official InsightFace weights used during current validation are restricted to
non-commercial research and development. Commercial deployment requires a
model with appropriate commercial rights or a corresponding license.
