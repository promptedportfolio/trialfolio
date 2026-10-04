"""Running Git in a test, outside the repository the tests run in."""

import os


def outside_any_repository() -> dict[str, str]:
    """The environment, without the variables that point Git at a repository, and without the
    user's Git configuration. A Git hook exports GIT_DIR, for example, which would otherwise
    point a test's Git commands at the developer's own repository."""
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    return environment | {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
