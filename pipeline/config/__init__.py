"""Config schemas and loader. See docs/DESIGN.md and `config/`."""

from .schema import Profile, Source, SourcesFile, Topic, TopicsFile
from .validate import Config, ConfigError, load_config

__all__ = [
    "Config",
    "ConfigError",
    "Profile",
    "Source",
    "SourcesFile",
    "Topic",
    "TopicsFile",
    "load_config",
]
