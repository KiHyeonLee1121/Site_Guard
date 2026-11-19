"""Download verified weights without installing a detector or using a GPU."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "models" / "local"
NATIVE_NAME = "SSD-Mobilenet-v2"


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def checked(path, value):
    return path.is_file() and digest(path) == value


def prepare(kind, package=None):
    key = {"jetson": "ssd-mobilenet-v2", "yolo": "yolo11n"}[kind]
    manifest = json.loads((ROOT / "models" / "manifest.json").read_text(encoding="utf-8"))[key]
    target = LOCAL / ("yolo11n.pt" if kind == "yolo" else "jetson")
    network = target / "networks"
    files = network / NATIVE_NAME
    if kind == "yolo" and checked(target, manifest["sha256"]):
        return target
    if (kind == "jetson" and (network / "models.json").is_file()
            and all(checked(files / name, value) for name, value in manifest["files"].items())):
        return target
    LOCAL.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".download-", dir=str(LOCAL)) as temp:
        archive = Path(temp) / "bundle"
        if package is None:
            request = Request(manifest["url"], headers={"User-Agent": "SiteGuard-model-prep/1.0"})
            with urlopen(request, timeout=60) as source, archive.open("wb") as destination:
                shutil.copyfileobj(source, destination)
        else:
            shutil.copyfile(str(package), str(archive))
        if not checked(archive, manifest["sha256"]):
            raise ValueError("Model SHA-256 mismatch. Check the supplied file or upstream release.")
        if kind == "yolo":
            archive.replace(target)
            return target
        items = manifest["files"]
        with tarfile.open(str(archive), "r:gz") as bundle:
            for name, expected in items.items():
                member = bundle.getmember(NATIVE_NAME + "/" + name)
                if not member.isfile():
                    raise ValueError("Invalid model archive member")
                with bundle.extractfile(member) as source, (Path(temp) / name).open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                if not checked(Path(temp) / name, expected):
                    raise ValueError("Checksum mismatch for " + name)
        files.mkdir(parents=True, exist_ok=True)
        for name in items:
            (Path(temp) / name).replace(files / name)
        registry = {"detection": {"siteguard-ssd-mobilenet-v2": {
            "dir": NATIVE_NAME, "model": "ssd_mobilenet_v2_coco.uff",
            "labels": "networks/" + NATIVE_NAME + "/ssd_coco_labels.txt",
            "input": "Input", "input_dims": [3, 300, 300],
            "output": {"bbox": "NMS", "count": "NMS_1"}
        }}}
        spec = Path(temp) / "models.json"
        spec.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        spec.replace(network / "models.json")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=("jetson", "yolo"))
    parser.add_argument("--from-file", type=Path, help="Provision from a locally copied upstream download")
    args = parser.parse_args()
    try:
        print(prepare(args.backend, args.from_file))
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(2, "Model preparation failed: {}\n".format(error))


if __name__ == "__main__":
    main()
