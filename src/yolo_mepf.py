"""YOLO MEPF fine-tune helpers (Phase C)."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MEPF_CLASSES = [
    "valve", "pump", "fcu", "ahu", "diffuser", "sprinkler",
    "smoke_detector", "panel", "fixture", "elbow", "tee", "reducer",
]


def resolve_weights_path(weights: str | None = None) -> str:
    if not weights:
        try:
            from src.config import settings
            weights = getattr(settings, "yolo_weights", "") or ""
        except Exception:
            weights = ""
    weights = (weights or os.environ.get("YOLO_WEIGHTS", "") or "").strip()
    if not weights:
        return "yolo11n.pt"
    if weights.startswith("s3://") or (not os.path.exists(weights) and "/" in weights):
        try:
            from src.storage import get_storage
            store = get_storage()
            key = weights.replace("s3://", "").split("/", 1)[-1] if weights.startswith("s3://") else weights
            return store.fetch_to_local(key)
        except Exception as e:
            logger.warning("Cannot fetch weights %s (%s) — fallback yolo11n.pt", weights, e)
            return "yolo11n.pt"
    return weights


def get_mepf_yolo(weights: str | None = None):
    from ultralytics import YOLO
    path = resolve_weights_path(weights)
    logger.info("Loading YOLO weights: %s", path)
    return YOLO(path)


def train_mepf(data_yaml: str, *, base_weights: str = "yolo11n.pt", epochs: int = 50, imgsz: int = 640, project: str = "runs/mepf", name: str = "train", device: str = "") -> str:
    from ultralytics import YOLO
    model = YOLO(base_weights)
    kwargs = {"data": data_yaml, "epochs": epochs, "imgsz": imgsz, "project": project, "name": name}
    if device:
        kwargs["device"] = device
    results = model.train(**kwargs)
    best = Path(project) / name / "weights" / "best.pt"
    if best.exists():
        return str(best)
    save_dir = getattr(results, "save_dir", None)
    if save_dir:
        candidate = Path(save_dir) / "weights" / "best.pt"
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("Không tìm thấy best.pt sau train.")


def write_default_data_yaml(out_dir: str = "data/yolo_mepf") -> str:
    root = Path(out_dir)
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(DEFAULT_MEPF_CLASSES))
    yaml_path = root / "data.yaml"
    yaml_path.write_text(
        f"""# MEPF YOLO dataset
path: {root.resolve()}
train: images/train
val: images/val

names:
{names}
""",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        """# YOLO MEPF dataset\n\n1. Xuất PNG từ DXF.\n2. Gán nhãn YOLO.\n3. Train: `uv run python -m src.yolo_mepf train --data data/yolo_mepf/data.yaml`\n4. `YOLO_WEIGHTS=runs/mepf/train/weights/best.pt`\n""",
        encoding="utf-8",
    )
    return str(yaml_path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="yolo_mepf")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_train = sub.add_parser("train")
    p_train.add_argument("--data", required=True)
    p_train.add_argument("--weights", default="yolo11n.pt")
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--imgsz", type=int, default=640)
    p_train.add_argument("--device", default="")
    p_sc = sub.add_parser("scaffold")
    p_sc.add_argument("--out", default="data/yolo_mepf")
    args = parser.parse_args(argv)
    if args.cmd == "scaffold":
        print(f"Scaffolded: {write_default_data_yaml(args.out)}")
    elif args.cmd == "train":
        print(f"BEST_WEIGHTS={train_mepf(args.data, base_weights=args.weights, epochs=args.epochs, imgsz=args.imgsz, device=args.device)}")


if __name__ == "__main__":
    main()
