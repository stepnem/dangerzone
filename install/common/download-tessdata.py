import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tarfile
import urllib.request

TESSDATA_RELEASES_URL = "https://api.github.com/repos/tesseract-ocr/tessdata_fast/releases/latest"
TESSDATA_ARCHIVE_URL = "https://github.com/tesseract-ocr/tessdata_fast/archive/{tessdata_version}/tessdata_fast-{tessdata_version}.tar.gz"
TESSDATA_CHECKSUM = "d0e3bb6f3b4e75748680524a1d116f2bfb145618f8ceed55b279d15098a530f9"


def git_root():
    """Get the root directory of the Git repo."""
    # FIXME: Use a Git Python binding for this.
    # FIXME: Make this work if called outside the repo.
    cmd = ["git", "rev-parse", "--show-toplevel"]
    path = subprocess.run(cmd, check=True, stdout=subprocess.PIPE).stdout.decode().strip("\n")
    return pathlib.Path(path)


def main():
    tessdata_dir = git_root() / "share" / "tessdata"

    # Download tessdata archive
    with urllib.request.urlopen(TESSDATA_RELEASES_URL) as f:
        resp = f.read()
        releases = json.loads(resp)
        tag = releases["tag_name"]

    print(f"> Downloading tessdata release {tag}", file=sys.stderr)
    archive_url = TESSDATA_ARCHIVE_URL.format(tessdata_version=tag)
    with urllib.request.urlopen(archive_url) as f:
        archive = f.read()
        digest = hashlib.sha256(archive).hexdigest()
        if digest != TESSDATA_CHECKSUM:
            raise RuntimeError(f"Checksum mismatch {digest} != {TESSDATA_CHECKSUM}")

    print(f"> Extracting tessdata archive into {tessdata_dir}", file=sys.stderr)
    with tarfile.open(fileobj=io.BytesIO(archive)) as t:
        def filter_traineddata(tarinfo: tarfile.TarInfo, path: str):
            tarinfo = tarfile.data_filter(tarinfo, path)
            regex = rf"^tessdata_fast-{tag}/[a-z_]+.traineddata$"
            if re.match(regex, tarinfo.name):
                new_name = tarinfo.name.split("/")[1]
                print(f">> Extracting {new_name} into {tessdata_dir}")
                return tarinfo.replace(name=new_name)

        t.extractall(path=tessdata_dir, filter=filter_traineddata)


if __name__ == "__main__":
    sys.exit(main())
