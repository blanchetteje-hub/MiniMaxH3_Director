"""Root pytest configuration for this ComfyUI custom-node repository.

The early plugin is necessary because pytest imports this directory's package
entrypoint before importing this conftest module.  Re-exporting the shims here
also gives tests one stable place from which to monkeypatch them.
"""

from pytest_comfy_stubs import comfy, folder_paths, server  # noqa: F401


collect_ignore = ["__init__.py", "nodes.py"]
