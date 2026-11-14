import os
def ctrl_prekey():
    v = os.environ.get("A9_PREKEY")
    if not v:
        raise SystemExit("A9_PREKEY not set")
    return v.encode()
