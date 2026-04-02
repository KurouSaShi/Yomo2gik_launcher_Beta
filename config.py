# config.py - ランチャー設定ファイル
# ここを自分のリポジトリ情報に変更してください

# =======================================
# GitHub リポジトリ設定
# =======================================
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main"

# update_manifest.json の URL (GitHub Raw)
MANIFEST_URL = f"{GITHUB_RAW_BASE}/update_manifest.json"

# =======================================
# ランチャー設定
# =======================================
LAUNCHER_VERSION = "1.0.0"         # 現在のランチャーバージョン
LAUNCHER_SCRIPT_NAME = "launcher.py"  # 自己更新時に置き換えるファイル名

# =======================================
# ゲーム設定
# =======================================
GAME_TITLE = "My Awesome Game"      # ゲームタイトル（UI表示用）
GAME_EXECUTABLE = "game/game.exe"   # 起動する実行ファイル（相対パス）
# macOS: "game/MyGame.app/Contents/MacOS/MyGame"
# Linux: "game/game"

# ゲームファイルのインストール先（ランチャーからの相対パス）
GAME_INSTALL_DIR = "."

# =======================================
# UI 設定
# =======================================
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 560