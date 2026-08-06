# FastVisionAI Architecture

## Design principles

FastVisionAI separates capture, inference orchestration and domain features.
Components depend on typed contracts rather than concrete ML frameworks. Camera
capture must remain usable when inference is disabled or fails.

Core principles are bounded memory, explicit cancellation, lazy resources,
observable execution, relative paths and backend independence. External Python
plugins are trusted code and must be installed deliberately by an administrator.

## Data flow

```text
Camera Service -> Frame -> FrameQueue -> MinimalPreprocessor -> PreparedFrame
                                                        |
                                                        v
                                               InferenceScheduler
                                                |      |      |
                                             Plugin Plugin Plugin
                                                        |
                                                        v
                                                 InferenceResult
```

`Frame` is the immutable link to the original image and capture metadata.
`PreparedFrame` keeps that reference while describing the data presented to an
inference backend. `InferenceResult` groups detections, metrics, latency,
backend identity and extensible attachments.

## Execution contracts

`InferenceBackend` is the only execution contract. Built-in modules, external
plugins and the scheduler all implement it. No separate plugin execution
interface exists.

`InferenceContext.run_id` correlates inference, metrics and logs. The context is
reserved for future runtime resources without coupling plugins to ONNX Runtime,
TensorRT or DeepStream today.

The sequential `InferenceScheduler` orders plugins by ascending priority and
then stable plugin ID. It aggregates detections and namespaces attachments by
plugin. Configurable error isolation allows later plugins to run after a failure.

## Model lifecycle

`ModelManager` registers versioned `ModelSpec` objects and resolves artifacts
relative to the project. A model moves through `UNREGISTERED`, `REGISTERED`,
`LOADED`, `UNLOADING` and `FAILED`. Loading is lazy and cached. Concrete
`ModelLoader` adapters will be supplied later for PyTorch, ONNX Runtime and
TensorRT; none are dependencies of the current infrastructure.

## Plugin lifecycle

`PluginManager` discovers built-in and external modules, validates a complete
`PluginDescriptor`, applies configuration, dynamically instantiates only enabled
plugins and caches loaded instances. Descriptors include identity, version,
author, backend, capabilities, priority and enabled state.

## Observability

`BenchmarkManager` produces immutable snapshots containing effective FPS,
pipeline latency, queue wait, total execution time, dropped frames and per-plugin
timings/errors. It has no database or API dependency.

## Current boundaries

The current engine uses synthetic images and `DummyPlugin`. It contains no real
model, YOLO, tracking, recognition, biometrics, GPU scheduling, API or GUI.
Future Jetson support will be implemented through backend and model-loader
adapters without changing Camera Service or inference contracts.

The first real-model adapter is `PersonDetectorPlugin`. It uses a logical model
alias, normalized boxes and a lazy `ModelLoader`; weights are never downloaded
automatically. Device `auto` is resolved by `ModelRuntime`.

`FaceDetectorPlugin` is an independent OpenCV YuNet backend. Its ONNX artifact
is resolved through `ModelManager`, loaded lazily and hashed with SHA-256. It
emits normalized face-only boxes for multiple faces and preserves five
normalized landmarks per detection in namespaced result attachments. The
landmarks are metadata only; no recognition or biometric processing is part of
the plugin.

## Runtime and events

`RuntimeRegistry` registers factories while `ModelRuntime` owns initialization,
preparation, inference and release. Typed `InternalEventBus` and
`ExternalEventBus` boundaries currently share a synchronous `EventBus`.
Architectural decisions are recorded under `docs/adr/`; plugin authors should
follow `PLUGIN_API.md`.
