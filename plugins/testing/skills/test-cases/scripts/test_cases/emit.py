import os
import tempfile
from pathlib import Path


def write_text(path, text):
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=parent, delete=False
    ) as f:
        f.write(text)
        tmp = f.name
    os.replace(tmp, path)


def write_outputs(out_dir, files):
    for name in sorted(files):
        write_text(Path(out_dir) / name, files[name])
