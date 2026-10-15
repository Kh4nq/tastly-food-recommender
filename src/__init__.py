"""Checkout compatibility for documented src.* public imports.

The installed packages remain common, conversation, retrieval, ranking and
pipeline. Alias their public modules to prevent duplicate Pydantic class
identities. Use canonical installed names for internal/submodule imports.
Requires the project installed (pip install -e '.[test]') or src on PYTHONPATH.
"""

from importlib import import_module as _import_module
import sys as _sys

for _name in (
    "common", "common.schemas", "common.constants", "common.config", "common.interfaces",
    "conversation", "retrieval", "ranking", "pipeline", "personalization",
):
    _module = _import_module(_name)
    _sys.modules[f"{__name__}.{_name}"] = _module
    if "." not in _name:
        globals()[_name] = _module

# Already imported submodules (e.g. state_manager) also retain their identities.
for _name, _module in list(_sys.modules.items()):
    if _name.partition(".")[0] in {"common", "conversation", "retrieval", "ranking", "pipeline", "personalization"}:
        _sys.modules[f"{__name__}.{_name}"] = _module

del _name, _module, _import_module, _sys
