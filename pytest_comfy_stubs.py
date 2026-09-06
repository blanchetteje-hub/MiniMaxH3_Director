"""Early pytest plugin that installs import-only ComfyUI test doubles."""

from __future__ import annotations

import os
import sys
import tempfile
import types


TEST_ROOT = os.path.join(tempfile.gettempdir(), "automate_git_pytest")
OUTPUT_DIR = os.path.join(TEST_ROOT, "output")
INPUT_DIR = os.path.join(TEST_ROOT, "input")
TEMP_DIR = os.path.join(TEST_ROOT, "temp")
USER_DIR = os.path.join(TEST_ROOT, "user")


def module(name: str) -> types.ModuleType:
    value = sys.modules.get(name)
    if value is None:
        value = types.ModuleType(name)
        sys.modules[name] = value
    return value


folder_paths = module("folder_paths")
folder_paths.base_path = TEST_ROOT
folder_paths.models_dir = os.path.join(TEST_ROOT, "models")
folder_paths.folder_names_and_paths = {}
folder_paths.get_output_directory = lambda: OUTPUT_DIR
folder_paths.get_input_directory = lambda: INPUT_DIR
folder_paths.get_temp_directory = lambda: TEMP_DIR
folder_paths.get_user_directory = lambda: USER_DIR
folder_paths.get_folder_paths = lambda _name: []
folder_paths.get_filename_list = lambda _name: []
folder_paths.get_full_path = lambda _name, _filename: None

module("nodes")

comfy = module("comfy")
comfy.__path__ = []
for submodule_name in ("utils", "model_management", "sd"):
    submodule = module(f"comfy.{submodule_name}")
    setattr(comfy, submodule_name, submodule)

comfy_nested_tensor = module("comfy.nested_tensor")


class NestedTensor:
    def __init__(self, tensors):
        self.tensors = tuple(tensors)
        self.is_nested = True


comfy_nested_tensor.NestedTensor = NestedTensor
comfy.nested_tensor = comfy_nested_tensor

server = module("server")


class PromptServer:
    instance = None


server.PromptServer = PromptServer
