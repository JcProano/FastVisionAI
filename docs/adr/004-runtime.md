# ADR 004: Runtime Execution Layer

Status: Accepted. `RuntimeRegistry` only creates implementations; `ModelRuntime`
owns preparation, inference, state transitions and release. Framework adapters
can be added without changing AIManager.
