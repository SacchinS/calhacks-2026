"""Set up the ASL Citizen sign model (2,731 signs) for recognition/asl_citizen.py, once.

    uv run --extra camera --with torch --with onnx \
        python tools/setup_asl_citizen.py --accept-license

Everything goes to models/asl_citizen/ (gitignored):
1. The ST-GCN model code from microsoft/ASL-citizen-code (MIT), pinned to one commit, and
   its trained weights from that repo's release (29 MB).
2. The word list: the dataset's split files, read out of the 46 GB dataset zip with range
   requests (about 14 MB, no videos). The model's outputs are the training set's glosses
   in sorted order. The dataset is under the Microsoft Research License Terms: research
   and non-commercial use only, and the data (this word list included) can't be shared.
   That's why it stays in models/ and why the tool asks for --accept-license.
3. The model exported to ONNX (stgcn.onnx), so the app runs it with ONNX Runtime, like
   the letter model, without torch. The export is checked against torch on random input.
"""

from __future__ import annotations

import argparse
import csv
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import ROOT  # noqa: E402

OUT = ROOT / "models" / "asl_citizen"
COMMIT = "17f0148b00ef87a5957ec103da8d10bd8eb1fa23"
CODE = f"https://raw.githubusercontent.com/microsoft/ASL-citizen-code/{COMMIT}/ST-GCN/architecture/"
ARCHITECTURE = ("fc.py", "graph_utils.py", "network.py", "st_gcn.py")
WEIGHTS = (
    "https://github.com/microsoft/ASL-citizen-code/releases/download/checkpoints_v1/"
    "ASL_citizen_stgcn_weights.zip"
)
DATASET = (
    "https://download.microsoft.com/download/b/8/8/b88c0bae-e6c1-43e1-8726-98cf5af36ca4/"
    "ASL_Citizen.zip"
)
# From ST-GCN/stgcn_testing.py: the 27-point graph the weights were trained on.
GRAPH = {
    "num_nodes": 27,
    "center": 0,
    "inward_edges": [
        [2, 0], [1, 0], [0, 3], [0, 4], [3, 5], [4, 6], [5, 7], [6, 17], [7, 8], [7, 9],
        [9, 10], [7, 11], [11, 12], [7, 13], [13, 14], [7, 15], [15, 16], [17, 18],
        [17, 19], [19, 20], [17, 21], [21, 22], [17, 23], [23, 24], [17, 25], [25, 26],
    ],
}  # fmt: skip
CLASSES = 2731
FRAMES, POINTS = 128, 27


class RangeFile(io.RawIOBase):
    """A remote file read with HTTP range requests, so zipfile can pick out members."""

    def __init__(self, url: str) -> None:
        self.url, self.pos, self.fetched = url, 0, 0
        head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"))
        self.size = int(head.headers["Content-Length"])

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, buffer) -> int:
        if self.pos >= self.size or not len(buffer):
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        request = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        data = urllib.request.urlopen(request).read()
        buffer[: len(data)] = data
        self.pos += len(data)
        self.fetched += len(data)
        return len(data)


def fetch_code() -> None:
    folder = OUT / "architecture"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").write_text("")
    for name in ARCHITECTURE:
        urllib.request.urlretrieve(CODE + name, folder / name)
    print(f"model code from microsoft/ASL-citizen-code@{COMMIT[:7]} -> {folder}")


def fetch_weights() -> Path:
    path = OUT / "ASL_citizen_stgcn_weights.pt"
    if not path.exists():
        print("downloading the weights (29 MB)...")
        with zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(WEIGHTS).read())) as z:
            (member,) = [n for n in z.namelist() if n.endswith(".pt")]
            with z.open(member) as src, path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return path


def fetch_glosses() -> list[str]:
    meta = OUT / "meta"
    if not (meta / "train.csv").exists():
        print("reading the split files out of the dataset zip...")
        meta.mkdir(parents=True, exist_ok=True)
        raw = RangeFile(DATASET)
        with zipfile.ZipFile(io.BufferedReader(raw, buffer_size=1 << 20)) as z:
            for name in z.namelist():
                if name.endswith((".csv", "use.txt")):
                    (meta / Path(name).name).write_bytes(z.read(name))
        print(f"  {raw.fetched / 1e6:.1f} MB read")
    with (meta / "train.csv").open() as f:
        rows = list(csv.reader(f))[1:]
    glosses = sorted({row[2].strip() for row in rows})  # as the training code orders them
    if len(glosses) != CLASSES:
        raise SystemExit(f"expected {CLASSES} glosses, found {len(glosses)}")
    (OUT / "glosses.txt").write_text("\n".join(glosses) + "\n")
    return glosses


def export(weights: Path) -> None:
    import numpy as np
    import onnxruntime as ort
    import torch

    sys.path.insert(0, str(OUT))
    from architecture.fc import FC
    from architecture.network import Network
    from architecture.st_gcn import STGCN

    model = Network(
        encoder=STGCN(in_channels=2, graph_args=GRAPH, edge_importance_weighting=True),
        decoder=FC(n_features=256, num_class=CLASSES, dropout_ratio=0.05),
    )
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict({k: v.float() for k, v in state.items()}, strict=True)
    model.eval()
    path = OUT / "stgcn.onnx"
    example = torch.zeros(1, 2, FRAMES, POINTS)
    torch.onnx.export(
        model, (example,), str(path), input_names=["pose"], output_names=["logits"],
        opset_version=17, dynamo=False,
    )  # fmt: skip
    check = torch.randn(1, 2, FRAMES, POINTS)
    with torch.no_grad():
        expected = model(check).numpy()
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    got = session.run(None, {"pose": check.numpy()})[0]
    diff = float(np.abs(got - expected).max())
    if diff > 1e-3:
        raise SystemExit(f"the ONNX export doesn't match torch (max difference {diff})")
    print(f"exported {path} ({path.stat().st_size / 1e6:.0f} MB), matches torch ({diff:.1e})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--accept-license",
        action="store_true",
        help="accept the ASL Citizen dataset's Microsoft Research License Terms",
    )
    args = parser.parse_args()
    if not args.accept_license:
        raise SystemExit(
            "The word list comes from the ASL Citizen dataset (Microsoft Research License "
            "Terms: research and non-commercial use only; the data can't be shared). Read "
            "them at https://www.microsoft.com/en-us/research/project/asl-citizen/ and run "
            "again with --accept-license."
        )
    OUT.mkdir(parents=True, exist_ok=True)
    fetch_code()
    weights = fetch_weights()
    glosses = fetch_glosses()
    print(f"{len(glosses)} glosses -> {OUT / 'glosses.txt'}")
    export(weights)
    print("Done. Turn it on with recognition.sign_models in config.yaml.")


if __name__ == "__main__":
    main()
