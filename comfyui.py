from __future__ import annotations

import subprocess
from pathlib import Path

import modal

from models import models, models_ext
from plugins import comfy_plugins

root_dir = Path(__file__).parent


def hf_download(
    repo_id: str,
    filename: str,
    model_dir: str = "/root/comfy/ComfyUI/models/checkpoints",
):
    import subprocess

    # Download model from Hugging Face
    from huggingface_hub import hf_hub_download

    model = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir="/cache",
    )

    Path(model_dir).mkdir(parents=True, exist_ok=True)
    local_filename = Path(filename).name
    target_path = Path(model_dir) / local_filename
    
    # Remove existing file/link if it exists to ensure fresh copy
    if target_path.exists() or target_path.is_symlink():
        target_path.unlink()
    
    _ = subprocess.run(
        f"cp -v {model} {model_dir}/{local_filename}",
        shell=True,
        check=True,
    )
    print(f"Downloaded {repo_id}/{filename} to {model_dir}/{local_filename}")
    
    # Special case: Gemma model needs an alias for workflow compatibility
    if "gemma" in filename.lower():
        alias_name = "comfy_gemma_3_12B_it.safetensors"
        alias_path = Path(model_dir) / alias_name
        if alias_path.exists() or alias_path.is_symlink():
            alias_path.unlink()
        _ = subprocess.run(
            f"cp -v {model} {model_dir}/{alias_name}",
            shell=True,
            check=True,
        )
        print(f"Created alias: {model_dir}/{alias_name} -> {local_filename}")


def download_external_model(url: str, filename: str, model_dir: str):
    import subprocess

    cache_dir = "/cache"
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    cached_path = Path(cache_dir) / filename
    if not cached_path.exists():
        print(f"Downloading {filename} from {url}...")
        _ = subprocess.run(
            [
                "aria2c",
                "--console-log-level=error",
                "--summary-interval=0",
                "-x",
                "16",
                "-s",
                "16",
                "-o",
                filename,
                "-d",
                cache_dir,
                url,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    Path(model_dir).mkdir(parents=True, exist_ok=True)
    target_path = Path(model_dir) / filename

    # Remove existing file/link if it exists to ensure fresh link
    if target_path.exists() or target_path.is_symlink():
        target_path.unlink()

    # Create symlink
    target_path.symlink_to(cached_path)
    print(f"Linked {filename} to {model_dir}/{filename}")


def download_all():
    for model in models:
        hf_download(model["repo_id"], model["filename"], model["model_dir"])

    for model in models_ext:
        download_external_model(model["url"], model["filename"], model["model_dir"])


vol = modal.Volume.from_name("hf-hub-cache", create_if_missing=True)

# construct images and install deps/custom nodes
image = (
    modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("models", "plugins", copy=True)
    .apt_install("git", "git-lfs", "libgl1-mesa-dev", "libglib2.0-0", "aria2")
    .pip_install_from_requirements(str(root_dir / "requirements_comfy.txt"))
    .run_commands("comfy --skip-prompt install --nvidia")
    .run_commands("git lfs install")
)

# download models
image = image.env({"HF_HUB_ENABLE_HF_TRANSFER": "1"}).run_function(
    download_all, volumes={"/cache": vol}, secrets=[modal.Secret.from_name("huggingface")]
)


# setup custom nodes - always install plugins regardless of workflow
image = image.run_commands("comfy node install " + " ".join(comfy_plugins))

# setup workflow if it exists - bake into image at build time
workflow_file_path = Path(__file__).parent / "workflow_api.json"
if workflow_file_path.exists():
    image = (
        image
        .add_local_file(workflow_file_path, "/root/workflow_api.json", copy=True)
        .run_commands(
            "mkdir -p /root/comfy/ComfyUI/user/default && "
            "cp /root/workflow_api.json /root/comfy/ComfyUI/user/default/workflow.json"
        )
    )
else:
    print(
        f"Warning: {workflow_file_path} not found. API endpoint might not work without a workflow."
    )

app = modal.App(name="modal-comfyui", image=image)


@app.function(
    volumes={"/cache": vol},
    secrets=[modal.Secret.from_name("huggingface")],
)
def download():
    """Download and cache all configured models."""
    download_all()
    print("All models downloaded successfully!")


@app.function(
    max_containers=1,
    gpu="L4",
    volumes={"/cache": vol},
    scaledown_window=60,  # idle 1 minutes to shutdown
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(max_inputs=10)
@modal.web_server(8000, startup_timeout=60)
def ui():
    _ = subprocess.Popen(
        "comfy launch --background -- --listen 0.0.0.0 --port 8000 --enable-manager", shell=True
    )
