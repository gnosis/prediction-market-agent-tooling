"""
Prediction Market Agent Tooling

This package provides tools and utilities for interacting with prediction markets.
"""

import pkgutil
import importlib
import sys

# Define all modules that should be available
__all__ = []

# Ensure package is importable from subdirectories
package_name = __name__

for loader, module_name, is_pkg in pkgutil.walk_packages(__path__, prefix=package_name + "."):
    try:
        imported_module = importlib.import_module(module_name)
        globals()[module_name.split(".")[-1]] = imported_module
        __all__.append(module_name.split(".")[-1])
    except ImportError as e:
        print(f"Warning: Could not import {module_name}: {e}")

# Recursively ensure all submodules are imported
def recursive_import(package):
    for loader, module_name, is_pkg in pkgutil.walk_packages(package.__path__, prefix=package.__name__ + "."):
        try:
            imported_module = importlib.import_module(module_name)
            globals()[module_name.split(".")[-1]] = imported_module
            __all__.append(module_name.split(".")[-1])
            if is_pkg:
                recursive_import(imported_module)  # Recursively import nested submodules
        except ImportError as e:
            print(f"Warning: Could not import {module_name}: {e}")

# Import all submodules recursively
recursive_import(importlib.import_module(package_name))

