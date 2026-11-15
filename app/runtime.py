"""Escolha de dispositivo/precisão e informações do ambiente.

O torch é importado dentro das funções para que os testes rápidos (que usam
dublês no lugar dos modelos) rodem sem ele instalado.
"""

from __future__ import annotations

import os
import platform


def configure_threads(num_threads: int) -> None:
    """Fixa o número de threads do PyTorch. Chame antes de carregar os modelos."""
    if num_threads <= 0:
        return
    # A inferência roda em threads do pool do Starlette; a variável de ambiente
    # garante que o OpenMP use o mesmo limite nelas, não só na thread principal.
    os.environ["OMP_NUM_THREADS"] = str(num_threads)
    import torch

    torch.set_num_threads(num_threads)


def pick_device(preference: str = "auto"):
    """Devolve (device, dtype): float32 na CPU, float16 só quando há CUDA."""
    import torch

    if preference == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("DEVICE=cuda, mas o PyTorch não encontrou CUDA nesta máquina")
    use_cuda = preference == "cuda" or (preference == "auto" and torch.cuda.is_available())
    if use_cuda:
        return torch.device("cuda"), torch.float16
    return torch.device("cpu"), torch.float32


def cpu_name() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def environment_info() -> dict:
    """CPU e versões das bibliotecas, para o /health e para o benchmark."""
    from importlib.metadata import PackageNotFoundError, version

    versoes = {"python": platform.python_version()}
    for pkg in ("torch", "torchvision", "transformers", "pillow", "fastapi"):
        try:
            versoes[pkg] = version(pkg)
        except PackageNotFoundError:
            versoes[pkg] = None

    threads = None
    if versoes["torch"]:
        import torch

        threads = torch.get_num_threads()
    return {
        "cpu": cpu_name(),
        "nucleos_logicos": os.cpu_count(),
        "threads_torch": threads,
        "versoes": versoes,
    }
