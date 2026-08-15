"""Administrative, non-biometric person-photo capture boundary."""

from .controller import PersonPhotoController
from .automatic import AutomaticPhotoPolicy, AutomaticPhotoSelector, AutomaticPhotoState

__all__ = ["PersonPhotoController", "AutomaticPhotoPolicy", "AutomaticPhotoSelector",
           "AutomaticPhotoState"]
