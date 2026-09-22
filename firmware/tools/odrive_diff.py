"""Recursively diff two ODrive backup-config JSON files."""
import json
import sys


def walk(a, b, path):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = path + "/" + k if path else k
            if k not in a:
                print("ONLY in NEW:", p, "=", json.dumps(b[k]))
            elif k not in b:
                print("ONLY in OLD:", p, "=", json.dumps(a[k]))
            else:
                walk(a[k], b[k], p)
    elif isinstance(a, bool) and isinstance(b, bool):
        if a != b:
            print(path, ": OLD=", a, " NEW=", b)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a != b:
            print(path, ": OLD=", a, " NEW=", b)
    elif a != b:
        print(path, ": OLD=", json.dumps(a), " NEW=", json.dumps(b))


def main():
    old = json.load(open(sys.argv[1], encoding="utf-8"))
    new = json.load(open(sys.argv[2], encoding="utf-8"))
    print("DIFF:", sys.argv[1], "->", sys.argv[2])
    walk(old, new, "")


if __name__ == "__main__":
    main()
