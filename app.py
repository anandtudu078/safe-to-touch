"""Hugging Face Space entrypoint (Gradio SDK, Blank template).

The Space runtime executes this file with the repo root as cwd and expects a
web server listening on 0.0.0.0:7860. We serve the FastAPI app, which mounts
the exported Next.js UI and the API on the same origin.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def ensure_demo_repo() -> None:
    """Bake the demo repo on first boot so the Space is demo-ready immediately."""
    default_repo = ROOT / "target-repo"
    repo = Path(os.environ.get("TARGET_REPO_PATH", str(default_repo)))
    if not repo.is_dir():
        subprocess.run(
            ["bash", str(ROOT / "scripts" / "create-demo-repo.sh"), str(repo)],
            check=True,
        )


def main() -> None:
    ensure_demo_repo()
    os.environ.setdefault("TARGET_REPO_PATH", str(ROOT / "target-repo"))
    import uvicorn

    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
