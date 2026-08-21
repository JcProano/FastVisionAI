"""Return the current immutable configuration snapshot."""

from ..domain.models import ConfigurationSnapshot
from .state import ConfigurationSession


class GetConfigurationUseCase:
    def __init__(self, session: ConfigurationSession) -> None:
        self._session = session

    def execute(self) -> ConfigurationSnapshot:
        return self._session.current()
