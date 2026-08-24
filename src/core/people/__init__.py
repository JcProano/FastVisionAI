"""People bounded context public API."""

from .application import *
from .domain import *
from .infrastructure import *
from .container import PeopleContainer

# Temporary compatibility name used by existing composition and tests.
PersonRepository = SQLitePeopleRepository
