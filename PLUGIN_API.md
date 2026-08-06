# FastVisionAI Plugin API 1.0

Plugins are trusted Python modules implementing only `InferenceBackend`. A module
exports `PLUGIN_DESCRIPTOR` and `create_plugin(settings)`.

```python
PLUGIN_DESCRIPTOR = PluginDescriptor(
    id="example", name="Example", version="1.0.0", api_version="1.0",
    author="Author", description="Purpose", backend="example",
    capabilities=(Capability("detection", "vision", False),),
    priority=100, enabled=False,
)

def create_plugin(settings: Mapping[str, Any], services: PluginServices) -> InferenceBackend: ...
```

`infer(PreparedFrame, InferenceContext) -> InferenceResult` must preserve the
original `Frame`. `InferenceContext.run_id` correlates logs and events.
`InferenceResult.attachments` stores namespaced embeddings, masks, OCR or other
future outputs. Plugins must validate settings, avoid absolute paths, release
optional resources through `release()`, and be compatible with Python 3.12.

Plugins are discovered in `src/engine/plugins` and configured external folders.
Only enabled plugins are instantiated. Lower `priority` executes first. Capability
IDs and categories must be non-empty and unique per descriptor. `experimental`
marks unstable behavior. `api_version` declares compatibility; breaking public
contract changes increment its major version.

Exceptions are isolated when `continue_on_error` is enabled. Plugins must not
open GUIs, mutate frames, assume GPU availability or install dependencies.
External modules execute trusted code during discovery and require administrator
review.

`PluginServices.model_manager` is the exclusive model lifecycle owner. Plugins
must use logical aliases rather than retain independently loaded model instances.
