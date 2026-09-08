"""Plugin registry and discovery.

Discovery is a directory scan plus decorator registration:
  - every module under plugins/builtin/ is imported once at startup;
  - a class decorated with @register instantiates and adds itself to the registry.

The agent's tool list and prompt lines are built from this registry at runtime,
so dropping a new file in plugins/builtin/ is all it takes to add a capability.

Why directory scan + decorator (and not entry points): this is a single
application, not a distributed plugin ecosystem. A scan is zero-config for the
common case and easy to read. Entry points would add packaging ceremony we
don't need here.
"""

from __future__ import annotations

import importlib
import pkgutil

from app.plugins.base import Plugin

_registry: dict[str, Plugin] = {}


def register(plugin_cls: type[Plugin]) -> type[Plugin]:
    """Class decorator: instantiate the plugin and register it by name."""
    instance = plugin_cls()
    if instance.name in _registry:
        raise ValueError(f"Duplicate plugin name: {instance.name!r}")
    _registry[instance.name] = instance
    return plugin_cls


def discover(package: str = "app.plugins.builtin") -> None:
    """Import every module in `package` so their @register decorators run.
    Call once at startup."""
    pkg = importlib.import_module(package)
    for _, module_name, _ in pkgutil.iter_modules(pkg.__path__, prefix=f"{package}."):
        importlib.import_module(module_name)


def all_plugins() -> list[Plugin]:
    return list(_registry.values())


def get(name: str) -> Plugin:
    if name not in _registry:
        raise KeyError(f"Unknown plugin: {name!r}. Registered: {list(_registry)}")
    return _registry[name]


def tool_schemas() -> list[dict]:
    """The LLM tool list, derived from the registry."""
    return [
        {"name": p.name, "description": p.description, "input_schema": p.input_schema}
        for p in all_plugins()
    ]
