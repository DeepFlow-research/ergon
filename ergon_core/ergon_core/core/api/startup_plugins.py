"""Optional startup plugin loader."""

from importlib import import_module


def run_startup_plugins(plugin_specs: tuple[str, ...]) -> None:
    for spec in plugin_specs:
        module_name, sep, attr_name = spec.partition(":")
        if not sep or not module_name or not attr_name:
            raise RuntimeError(
                f"Invalid ERGON_STARTUP_PLUGINS entry {spec!r}; expected 'module:function'"
            )
        module = import_module(module_name)
        plugin = getattr(module, attr_name)
        plugin()
