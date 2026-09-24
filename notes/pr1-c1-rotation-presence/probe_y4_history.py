"""H1 historical-control probe (READ ONLY): does the post-erratum code still rebuild
the historical Y4 records?

Does not modify anything.  Records the historical artifact hashes (proof the bytes are
untouched) and attempts load_package/load_result with the current (post-erratum) code.
"""
import hashlib
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from tools.y4_dry_runner import load_package, load_result

RUN = os.environ.get("AEDL_Y4_RUN", r"C:\Users\Ryan Gosling\Desktop\workspace\project_020_AEDL\gh56-y4-dry\r21\run")


def main():
    dirs = sorted(d for d in os.listdir(RUN) if os.path.isdir(os.path.join(RUN, d)))
    pkg_ok = pkg_fail = res_ok = res_fail = missing = 0
    first_error = None
    manifest = []
    for name in dirs:
        pdir = os.path.join(RUN, name)
        pkg_path = os.path.join(pdir, "package.json")
        res_path = os.path.join(pdir, "result.json")
        if not (os.path.isfile(pkg_path) and os.path.isfile(res_path)):
            missing += 1
            continue
        pkg_raw = open(pkg_path, "rb").read()
        res_raw = open(res_path, "rb").read()
        pkg_sha = hashlib.sha256(pkg_raw).hexdigest()
        manifest.append([name, pkg_sha, hashlib.sha256(res_raw).hexdigest()])
        try:
            doc = load_package(pkg_raw, pkg_sha)
            pkg_ok += 1
        except Exception as exc:
            pkg_fail += 1
            if first_error is None:
                first_error = "%s: %s: %s" % (name, type(exc).__name__, exc)
            continue
        try:
            load_result(res_raw, doc, pkg_sha)
            res_ok += 1
        except Exception as exc:
            res_fail += 1
            if first_error is None:
                first_error = "%s: %s: %s" % (name, type(exc).__name__, exc)
    print("historical record dirs        :", len(dirs))
    print("  without package+result pair :", missing)
    print("load_package rebuilt OK       :", pkg_ok)
    print("load_package REFUSED          :", pkg_fail)
    print("load_result rebuilt OK        :", res_ok)
    print("load_result REFUSED           :", res_fail)
    print("first refusal                 :", first_error)
    print("")
    print("artifact hashes (name, package.sha256, result.sha256) -- bytes untouched:")
    for row in manifest:
        print("  %s  %s  %s" % tuple(row))


if __name__ == "__main__":
    main()
