"""
gen_manifest.py - update_manifest.json の生成補助ツール（ZIP版）

使い方:
    python gen_manifest.py \
        --game-version 1.2.0 \
        --zip-path ./dist/game_v1.2.0.zip \
        --zip-url https://github.com/USER/REPO/releases/download/v1.2.0/game_v1.2.0.zip \
        --extract-to game

これを実行すると:
  - ZIPのSHA256を計算
  - update_manifest.json を更新
  - GitHubにpushすればOK

GitHub Releases にZIPをアップロードして、そのURLを --zip-url に渡してください。
（GitHub Raw ではなく Releases の方が大きなファイルに向いています）
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import date

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main"
LAUNCHER_VERSION = "1.0.0"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="update_manifest.json を生成します")
    ap.add_argument("--game-version",     required=True,  help="ゲームバージョン (例: 1.2.0)")
    ap.add_argument("--zip-path",         required=True,  help="ZIPファイルのローカルパス")
    ap.add_argument("--zip-url",          required=True,  help="ZIPのダウンロードURL (GitHub Releases)")
    ap.add_argument("--extract-to",       default="game", help="ZIP展開先ディレクトリ名 (default: game)")
    ap.add_argument("--launcher-version", default=LAUNCHER_VERSION)
    ap.add_argument("--output",           default="update_manifest.json")
    args = ap.parse_args()

    if not os.path.exists(args.zip_path):
        print(f"エラー: ZIPファイルが見つかりません: {args.zip_path}", file=sys.stderr)
        sys.exit(1)

    print(f"SHA256を計算中: {args.zip_path} ...")
    zip_hash = sha256(args.zip_path)
    zip_size = os.path.getsize(args.zip_path)
    print(f"  SHA256 : {zip_hash}")
    print(f"  サイズ : {zip_size / 1048576:.2f} MB")

    existing_notes = []
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            existing = json.load(f)
            existing_notes = existing.get("patch_notes", [])

    if not any(n["version"] == args.game_version for n in existing_notes):
        existing_notes.insert(0, {
            "version": args.game_version,
            "date": date.today().isoformat(),
            "changes": ["ここに変更内容を書いてください"]
        })
        print(f"\n⚠  patch_notes に v{args.game_version} を追加しました。")
        print(f"   {args.output} を開いて変更内容を記入してください。\n")

    manifest = {
        "launcher_version": args.launcher_version,
        "launcher_download_url": f"{GITHUB_RAW_BASE}/launcher.py",
        "game_version": args.game_version,
        "zip": {
            "download_url": args.zip_url,
            "sha256": zip_hash,
            "size": zip_size,
            "extract_to": args.extract_to
        },
        "patch_notes": existing_notes
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"✓ {args.output} を生成しました")
    print()
    print("次のステップ:")
    print(f"  1. {args.output} のpatch_notesに変更内容を記入")
    print(f"  2. GitHub Releases に {os.path.basename(args.zip_path)} をアップロード")
    print(f"  3. {args.output} をGitHubにpush")


if __name__ == "__main__":
    main()