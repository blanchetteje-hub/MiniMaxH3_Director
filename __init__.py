import os
import re

import folder_paths
from safetensors.torch import save_file, load_file

import comfy.nested_tensor


def _safe_prefix(value):
    value = str(value or "h3_context/segment").replace("\\", "/").strip("/")
    if not value:
        value = "h3_context/segment"

    if ".." in value.split("/"):
        raise ValueError("filename_prefix may not contain '..'")

    value = re.sub(r"[^A-Za-z0-9_./-]", "_", value)
    return value


def _latent_path(filename_prefix, clip_index):
    prefix = _safe_prefix(filename_prefix)

    output_root = folder_paths.get_output_directory()

    relative_path = (
        f"{prefix}_{int(clip_index):05d}.safetensors"
    )

    path = os.path.abspath(
        os.path.join(output_root, relative_path)
    )

    output_root = os.path.abspath(output_root)

    if os.path.commonpath([path, output_root]) != output_root:
        raise ValueError("Resolved latent path escaped ComfyUI output directory")

    return path


def _extract_av_streams(latent):
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError("Expected a MiniMax H3 LATENT dictionary")

    samples = latent["samples"]

    if getattr(samples, "is_nested", False):
        tensors = list(samples.tensors)

    elif isinstance(samples, (tuple, list)):
        tensors = list(samples)

    elif hasattr(samples, "unbind"):
        tensors = list(samples.unbind())

    else:
        raise ValueError(
            "Expected MiniMax H3 joint video/audio latent; "
            f"received samples type {type(samples)!r}"
        )

    if len(tensors) < 2:
        raise ValueError(
            "MiniMax H3 latent has no audio stream. "
            "Connect the actual SamplerCustomAdvanced H3 AV output."
        )

    video = tensors[0]
    audio = tensors[1]

    if video.ndim != 5:
        raise ValueError(
            "Expected H3 video latent [B,C,T,H,W], "
            f"received shape {tuple(video.shape)}"
        )

    if audio.ndim != 4:
        raise ValueError(
            "Expected H3 audio latent [B,C,2,T], "
            f"received shape {tuple(audio.shape)}"
        )

    return video, audio


class MiniMaxH3AVSaveLatentForExtend:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT",),
                "filename_prefix": (
                    "STRING",
                    {"default": "h3_context/segment"},
                ),
                "clip_index": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 99999,
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("latent_path",)

    FUNCTION = "save"
    OUTPUT_NODE = True

    CATEGORY = "conditioning/minimax"

    def save(
        self,
        latent,
        filename_prefix="h3_context/segment",
        clip_index=1,
    ):
        video, audio = _extract_av_streams(latent)

        path = _latent_path(filename_prefix, clip_index)

        os.makedirs(
            os.path.dirname(path),
            exist_ok=True,
        )

        save_file(
            {
                "video": video.detach().cpu().contiguous(),
                "audio": audio.detach().cpu().contiguous(),
            },
            path,
            metadata={
                "format": "minimax_h3_av_v1",
                "clip_index": str(int(clip_index)),
            },
        )

        print(
            f"H3 AV latent saved: {path} "
            f"(video={tuple(video.shape)}, "
            f"audio={tuple(audio.shape)})"
        )

        return (path,)


class MiniMaxH3AVLoadLatentForExtend:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "filename_prefix": (
                    "STRING",
                    {"default": "h3_context/segment"},
                ),
                "clip_index": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 99999,
                    },
                ),
            }
        }

    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("av_latent",)

    FUNCTION = "load"

    CATEGORY = "conditioning/minimax"

    @classmethod
    def IS_CHANGED(
        cls,
        filename_prefix="h3_context/segment",
        clip_index=1,
    ):
        try:
            path = _latent_path(
                filename_prefix,
                clip_index,
            )
            return os.stat(path).st_mtime_ns
        except Exception:
            return float("NaN")

    def load(
        self,
        filename_prefix="h3_context/segment",
        clip_index=1,
    ):
        path = _latent_path(
            filename_prefix,
            clip_index,
        )

        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"H3 AV latent does not exist: {path}"
            )

        data = load_file(path)

        if "video" not in data or "audio" not in data:
            raise ValueError(
                f"{path} is not an H3 AV latent checkpoint"
            )

        samples = comfy.nested_tensor.NestedTensor(
            (
                data["video"],
                data["audio"],
            )
        )

        print(
            f"H3 AV latent loaded: {path} "
            f"(video={tuple(data['video'].shape)}, "
            f"audio={tuple(data['audio'].shape)})"
        )

        return (
            {
                "samples": samples,
            },
        )


NODE_CLASS_MAPPINGS = {
    "MiniMaxH3AVSaveLatentForExtend":
        MiniMaxH3AVSaveLatentForExtend,

    "MiniMaxH3AVLoadLatentForExtend":
        MiniMaxH3AVLoadLatentForExtend,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3AVSaveLatentForExtend":
        "H3 AV Save Latent",

    "MiniMaxH3AVLoadLatentForExtend":
        "H3 AV Load Latent",
}