# Hermes loads a directory plugin by exec'ing this file and calling `register`. The real code lives in
# the `pumpup_hermes` subpackage (a clean, testable import target). The import is deferred into register()
# so this file is import-safe outside the host's package context (e.g. when pytest imports the plugin root).
def register(ctx):
    """Plugin entry point — delegates to the pumpup_hermes package's register()."""
    from .pumpup_hermes import register as _register

    _register(ctx)


__all__ = ["register"]
