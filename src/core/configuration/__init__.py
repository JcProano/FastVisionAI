"""Configuration lifecycle bounded context."""

from .application import *
from .domain import *
from .diff import configuration_diff
from .infrastructure import (
    AtomicConfigurationStore,
    JSONConfigurationLoader,
    ProjectConfigurationPolicy,
)
from .profiles import ProfileRegistry
from .service import ConfigurationService
from .validators import ConfigurationValidator, known_only, redact

# Temporary compatibility name used by composition and historical tests.
ConfigurationLoader = JSONConfigurationLoader
