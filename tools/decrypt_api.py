"""Decrypt the portal's encrypted API responses (diagnostic CLI).

Usage:
    .venv\\Scripts\\python.exe tools\\decrypt_api.py [file1.json file2.json ...]

With no args, decrypts every tools/dumps/api/*classroom_works*.json.
The decryption logic lives in app/automation/portal_crypto.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.automation.portal_crypto import decrypt_cryptojs  # noqa: E402


def main() -> None:
    api_dir = Path(__file__).parent / "dumps" / "api"
    if len(sys.argv) > 1:
        files = [Path(p) for p in sys.argv[1:]]
    else:
        files = sorted(api_dir.glob("*classroom_works*.json"))
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8")).get("response", "")
        if not payload:
            print(f"== {path.name}: empty")
            continue
        try:
            text = decrypt_cryptojs(payload)
            data = json.loads(text)
            print(f"== {path.name}")
            print(json.dumps(data, indent=2)[:4000])
        except Exception as exc:
            print(f"== {path.name}: FAILED ({exc})")


if __name__ == "__main__":
    main()
