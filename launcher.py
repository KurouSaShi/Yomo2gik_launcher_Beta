"""
launcher.py - ゲームランチャー本体
PyQt6を使用。PySide6に切り替える場合はimport行を変更するだけでOK。

更新フロー:
  1. GitHubからupdate_manifest.jsonを取得
  2. ランチャーバージョンを比較 → 古ければ自己更新して再起動
  3. ゲームバージョンを比較（またはZIPのSHA256）→ 差分があればZIPをDL
  4. ZIPを検証・展開してインストール完了
  ※ 差分判定: ローカルのgame_version.txtとmanifestのgame_versionを比較
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

import requests
from packaging.version import Version

# --- PyQt6 / PySide6 切り替え ---
try:
    from PyQt6.QtCore import (
        QObject, QRunnable, QThread, QThreadPool, Qt, QTimer, pyqtSignal
    )
    from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPalette
    from PyQt6.QtWidgets import (
        QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
        QMessageBox, QProgressBar, QPushButton, QScrollArea,
        QSizePolicy, QTextBrowser, QVBoxLayout, QWidget,
    )
    Signal = pyqtSignal
except ImportError:
    from PySide6.QtCore import (
        QObject, QRunnable, QThread, QThreadPool, Qt, QTimer, Signal
    )
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPalette
    from PySide6.QtWidgets import (
        QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
        QMessageBox, QProgressBar, QPushButton, QScrollArea,
        QSizePolicy, QTextBrowser, QVBoxLayout, QWidget,
    )

import config

# =====================================================================
# スタイルシート（ダーク・ゲーミングテーマ）
# =====================================================================
STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0d0d14;
    color: #e0e0f0;
    font-family: 'Segoe UI', 'Yu Gothic UI', sans-serif;
    font-size: 13px;
}

/* ヘッダー */
#header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0d0d14, stop:0.5 #131325, stop:1 #0d0d14);
    border-bottom: 1px solid #2a2a4a;
}

#titleLabel {
    font-size: 28px;
    font-weight: bold;
    color: #c8aaff;
    letter-spacing: 3px;
}

#versionLabel {
    font-size: 11px;
    color: #5a5a8a;
}

/* パッチノートパネル */
#patchPanel {
    background-color: #0f0f1e;
    border: 1px solid #1e1e3a;
    border-radius: 6px;
}

#patchTitle {
    font-size: 12px;
    font-weight: bold;
    color: #7a6aaa;
    letter-spacing: 2px;
    padding: 8px 12px 4px 12px;
    border-bottom: 1px solid #1e1e3a;
}

QTextBrowser {
    background-color: transparent;
    color: #b0b0cc;
    border: none;
    font-size: 12px;
    line-height: 1.6;
}

/* ステータスバー */
#statusBar {
    background-color: #080810;
    border-top: 1px solid #1e1e3a;
    padding: 0 16px;
}

#statusLabel {
    color: #6060a0;
    font-size: 11px;
}

/* プログレスバー */
QProgressBar {
    background-color: #15152a;
    border: 1px solid #2a2a4a;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6633cc, stop:1 #aa44ff);
    border-radius: 3px;
}

/* ボタン */
#launchBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7744ee, stop:1 #5522cc);
    color: #ffffff;
    border: none;
    border-radius: 4px;
    font-size: 15px;
    font-weight: bold;
    letter-spacing: 2px;
    padding: 12px 40px;
    min-width: 160px;
}
#launchBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #9966ff, stop:1 #7744ee);
}
#launchBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #5522cc, stop:1 #4411aa);
}
#launchBtn:disabled {
    background: #2a2a3a;
    color: #4a4a6a;
}

#updateBtn {
    background: transparent;
    color: #7a5acc;
    border: 1px solid #3a2a6a;
    border-radius: 4px;
    font-size: 12px;
    padding: 8px 20px;
}
#updateBtn:hover {
    background: #1a1a2e;
    border-color: #6a4acc;
    color: #aa88ff;
}
#updateBtn:disabled {
    color: #3a3a5a;
    border-color: #2a2a3a;
}

/* セパレーター */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #1e1e3a;
}

/* スクロールバー */
QScrollBar:vertical {
    background: #0d0d14;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #2a2a4a;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ゲームバージョンバッジ */
#gameBadge {
    background-color: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 3px;
    color: #6060a0;
    font-size: 11px;
    padding: 3px 8px;
}
"""


# =====================================================================
# ユーティリティ
# =====================================================================


# ローカルにインストール済みのゲームバージョンを保存するファイル
INSTALLED_VERSION_FILE = os.path.join(config.GAME_INSTALL_DIR, ".game_version")


def sha256_of_file(path: str) -> str:
    """ファイルのSHA256ハッシュを返す"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_installed_version() -> str:
    """インストール済みゲームバージョンを返す。未インストールは '0.0.0'"""
    try:
        with open(INSTALLED_VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"


def save_installed_version(version: str):
    """インストール済みバージョンを保存"""
    os.makedirs(os.path.dirname(INSTALLED_VERSION_FILE) or ".", exist_ok=True)
    with open(INSTALLED_VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(version)


def download_file(url: str, dest: str, progress_cb=None, chunk_size: int = 65536):
    """URLからファイルをダウンロード。progress_cb(downloaded_bytes, total_bytes)"""
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    done = 0
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size):
            if chunk:
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)


# =====================================================================
# ワーカーシグナル
# =====================================================================

class WorkerSignals(QObject):
    finished   = Signal(object)   # 結果オブジェクト
    error      = Signal(str)      # エラーメッセージ
    progress   = Signal(int, int, str)  # (current, total, label)
    log        = Signal(str)


# =====================================================================
# 更新チェック・実行ワーカー
# =====================================================================

class CheckUpdateWorker(QRunnable):
    """マニフェストを取得して更新が必要かチェック"""

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.log.emit("マニフェストを確認中...")
            r = requests.get(config.MANIFEST_URL, timeout=15)
            r.raise_for_status()
            manifest = r.json()
            self.signals.finished.emit(manifest)
        except Exception as e:
            self.signals.error.emit(f"マニフェスト取得エラー: {e}")


class ZipUpdateWorker(QRunnable):
    """
    ゲームZIPをダウンロード → SHA256検証 → 展開 → バージョン保存

    manifest の zip ブロック:
    {
        "download_url": "https://..../game_v1.2.0.zip",
        "sha256": "abc123...",
        "size": 52428800,
        "extract_to": "game"   # 展開先ディレクトリ（GAME_INSTALL_DIR からの相対）
    }
    """

    def __init__(self, zip_info: dict, game_version: str, install_dir: str):
        super().__init__()
        self.zip_info     = zip_info
        self.game_version = game_version
        self.install_dir  = install_dir
        self.signals      = WorkerSignals()

    def run(self):
        url       = self.zip_info["download_url"]
        expected  = self.zip_info["sha256"]
        extract_to = os.path.join(
            self.install_dir,
            self.zip_info.get("extract_to", "game")
        )

        # ─── 1. ダウンロード ───
        tmp_zip = os.path.join(tempfile.gettempdir(), "game_update.zip")
        self.signals.log.emit("ZIPをダウンロード中...")

        try:
            def _prog(done, total):
                if total > 0:
                    pct = int(done / total * 100)
                    mb_done  = done  / 1048576
                    mb_total = total / 1048576
                    self.signals.progress.emit(
                        pct, 100,
                        f"{mb_done:.1f} MB / {mb_total:.1f} MB"
                    )

            download_file(url, tmp_zip, progress_cb=_prog)
        except Exception as e:
            self.signals.error.emit(f"ダウンロード失敗: {e}")
            return

        # ─── 2. SHA256 検証 ───
        self.signals.log.emit("ハッシュを検証中...")
        self.signals.progress.emit(100, 100, "検証中...")
        actual = sha256_of_file(tmp_zip)
        if actual.lower() != expected.lower():
            os.remove(tmp_zip)
            self.signals.error.emit(
                f"ZIPのハッシュが一致しません。\n"
                f"期待値: {expected}\n実際: {actual}\n\n"
                "ファイルが破損している可能性があります。"
            )
            return

        # ─── 3. 旧ゲームファイルを退避 ───
        backup_dir = extract_to + ".bak"
        if os.path.exists(extract_to):
            self.signals.log.emit("旧バージョンをバックアップ中...")
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
            shutil.copytree(extract_to, backup_dir)

        # ─── 4. 展開 ───
        self.signals.log.emit("ZIPを展開中...")
        try:
            if os.path.exists(extract_to):
                shutil.rmtree(extract_to)
            os.makedirs(extract_to, exist_ok=True)

            with zipfile.ZipFile(tmp_zip, "r") as zf:
                members = zf.infolist()
                total   = len(members)
                for i, member in enumerate(members):
                    zf.extract(member, extract_to)
                    self.signals.progress.emit(
                        int((i + 1) / total * 100), 100,
                        f"展開中: {member.filename}"
                    )

        except Exception as e:
            # 展開失敗 → バックアップから復元
            self.signals.log.emit("展開失敗。バックアップから復元中...")
            if os.path.exists(backup_dir):
                if os.path.exists(extract_to):
                    shutil.rmtree(extract_to)
                shutil.copytree(backup_dir, extract_to)
            self.signals.error.emit(f"ZIPの展開に失敗しました: {e}")
            return
        finally:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)

        # ─── 5. バックアップ削除 & バージョン保存 ───
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)

        save_installed_version(self.game_version)
        self.signals.progress.emit(100, 100, "完了")
        self.signals.finished.emit(True)


class SelfUpdateWorker(QRunnable):
    """ランチャー自身を更新して再起動"""

    def __init__(self, download_url: str):
        super().__init__()
        self.download_url = download_url
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.log.emit("ランチャーを更新中...")
            script_path = os.path.abspath(sys.argv[0])
            backup_path = script_path + ".bak"

            # バックアップ
            shutil.copy2(script_path, backup_path)

            # ダウンロード
            tmp = script_path + ".new"
            download_file(self.download_url, tmp)

            # 置き換え
            shutil.move(tmp, script_path)

            self.signals.log.emit("再起動します...")
            time.sleep(1)

            # 再起動
            python = sys.executable
            os.execv(python, [python] + sys.argv)

        except Exception as e:
            self.signals.error.emit(f"自己更新エラー: {e}")


# =====================================================================
# メインウィンドウ
# =====================================================================

class LauncherWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.manifest: dict | None = None
        self.needs_update: bool = False   # ゲームの更新が必要か
        self.zip_info: dict | None = None # manifest の zip ブロック
        self.pool = QThreadPool.globalInstance()
        self._build_ui()
        self._check_updates()

    # ------------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle(config.GAME_TITLE)
        self.setFixedSize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        # ── メインエリア ──
        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(14)

        body.addWidget(self._make_patch_panel(), 1)
        body.addLayout(self._make_right_panel())

        root.addLayout(body, 1)
        root.addWidget(self._make_status_bar())

    def _make_header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("header")
        w.setFixedHeight(80)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(24, 0, 24, 0)

        title = QLabel(config.GAME_TITLE.upper())
        title.setObjectName("titleLabel")
        lay.addWidget(title)
        lay.addStretch()

        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.launcherVerLabel = QLabel(f"Launcher v{config.LAUNCHER_VERSION}")
        self.launcherVerLabel.setObjectName("versionLabel")
        right.addWidget(self.launcherVerLabel)

        self.gameVerLabel = QLabel("Game v—")
        self.gameVerLabel.setObjectName("gameBadge")
        self.gameVerLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(self.gameVerLabel)

        lay.addLayout(right)
        return w

    def _make_patch_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("patchPanel")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lbl = QLabel("PATCH NOTES")
        lbl.setObjectName("patchTitle")
        lay.addWidget(lbl)

        self.patchBrowser = QTextBrowser()
        self.patchBrowser.setOpenExternalLinks(False)
        self.patchBrowser.setPlaceholderText("マニフェストを取得中...")
        lay.addWidget(self.patchBrowser, 1)
        return w

    def _make_right_panel(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(10)

        # ── ランチャー更新ボタン ──
        self.launcherUpdateBtn = QPushButton("⬆  ランチャーを更新")
        self.launcherUpdateBtn.setObjectName("updateBtn")
        self.launcherUpdateBtn.setEnabled(False)
        self.launcherUpdateBtn.clicked.connect(self._do_self_update)
        lay.addWidget(self.launcherUpdateBtn)

        lay.addStretch()

        # ── ゲーム更新ボタン ──
        self.updateBtn = QPushButton("ゲームを更新")
        self.updateBtn.setObjectName("updateBtn")
        self.updateBtn.setEnabled(False)
        self.updateBtn.clicked.connect(self._do_game_update)
        lay.addWidget(self.updateBtn)

        # ── 起動ボタン ──
        self.launchBtn = QPushButton("▶  起動")
        self.launchBtn.setObjectName("launchBtn")
        self.launchBtn.setEnabled(False)
        self.launchBtn.clicked.connect(self._launch_game)
        lay.addWidget(self.launchBtn)

        return lay

    def _make_status_bar(self) -> QWidget:
        w = QWidget()
        w.setObjectName("statusBar")
        w.setFixedHeight(50)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(3)

        self.statusLabel = QLabel("マニフェストを確認中...")
        self.statusLabel.setObjectName("statusLabel")
        lay.addWidget(self.statusLabel)

        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.setFixedHeight(6)
        self.progressBar.setTextVisible(False)
        lay.addWidget(self.progressBar)
        return w

    # ------------------------------------------------------------------
    # 更新チェック
    # ------------------------------------------------------------------

    def _check_updates(self):
        worker = CheckUpdateWorker()
        worker.signals.finished.connect(self._on_manifest_received)
        worker.signals.error.connect(self._on_error)
        worker.signals.log.connect(self._set_status)
        self.pool.start(worker)

    def _on_manifest_received(self, manifest: dict):
        self.manifest = manifest
        game_ver = manifest.get("game_version", "?")
        self.gameVerLabel.setText(f"Game v{game_ver}")
        self._render_patch_notes(manifest.get("patch_notes", []))

        # ── ランチャー自己更新チェック ──
        remote_launcher = manifest.get("launcher_version", "0.0.0")
        if Version(remote_launcher) > Version(config.LAUNCHER_VERSION):
            self.launcherUpdateBtn.setEnabled(True)
            self.launcherUpdateBtn.setText(
                f"⬆  ランチャーを更新  →  v{remote_launcher}"
            )
            self._set_status(f"ランチャーの新バージョンがあります: v{remote_launcher}")

        # ── ゲームZIP差分チェック ──
        # 判定ロジック:
        #   1. インストール済みバージョンとmanifestのgame_versionを比較
        #   2. バージョンが同じでもZIPのSHA256が違えば更新（ZIPの再配布時など）
        self.zip_info = manifest.get("zip")
        installed_ver = get_installed_version()
        self.needs_update = False

        if not self.zip_info:
            self._set_status("⚠ マニフェストにzipセクションがありません")
            self.progressBar.setValue(100)
            return

        exe_path = os.path.join(config.GAME_INSTALL_DIR, config.GAME_EXECUTABLE)
        game_installed = os.path.exists(exe_path)

        if not game_installed:
            # 未インストール
            self.needs_update = True
            self.updateBtn.setEnabled(True)
            self.updateBtn.setText("ゲームをインストール")
            self._set_status("ゲームがインストールされていません。")
        elif Version(game_ver) > Version(installed_ver):
            # バージョンアップ
            self.needs_update = True
            self.updateBtn.setEnabled(True)
            self.updateBtn.setText(
                f"ゲームを更新  v{installed_ver} → v{game_ver}"
            )
            self._set_status(
                f"新しいバージョンがあります: v{installed_ver} → v{game_ver}"
            )
        else:
            # バージョンが同じでもZIPのSHA256でZIPファイルのキャッシュ確認
            cached_zip = os.path.join(tempfile.gettempdir(), "game_update.zip")
            if (os.path.exists(cached_zip) and
                    sha256_of_file(cached_zip).lower() == self.zip_info["sha256"].lower()):
                pass  # キャッシュあり（通常は気にしない）
            self.launchBtn.setEnabled(True)
            self._set_status("ゲームは最新の状態です。いつでも起動できます。")

        if game_installed:
            self.launchBtn.setEnabled(True)

        self.progressBar.setValue(100)

    def _render_patch_notes(self, notes: list):
        html_parts = []
        for note in notes:
            ver  = note.get("version", "?")
            date = note.get("date", "")
            changes = note.get("changes", [])
            items = "".join(
                f'<li style="margin:3px 0;color:#a0a0c0;">{c}</li>'
                for c in changes
            )
            html_parts.append(f"""
                <div style="margin-bottom:16px;">
                  <span style="color:#c8aaff;font-weight:bold;font-size:14px;">
                    v{ver}
                  </span>
                  <span style="color:#3a3a6a;font-size:11px;margin-left:8px;">{date}</span>
                  <ul style="margin:6px 0 0 0;padding-left:18px;">{items}</ul>
                </div>
            """)
        self.patchBrowser.setHtml(
            '<div style="padding:10px;">' + "".join(html_parts) + "</div>"
        )

    # ------------------------------------------------------------------
    # ゲームファイル更新
    # ------------------------------------------------------------------

    def _do_game_update(self):
        if not self.zip_info:
            return
        self.updateBtn.setEnabled(False)
        self.launchBtn.setEnabled(False)
        self.launcherUpdateBtn.setEnabled(False)
        self.progressBar.setValue(0)

        game_ver = self.manifest.get("game_version", "0.0.0")
        worker = ZipUpdateWorker(self.zip_info, game_ver, config.GAME_INSTALL_DIR)
        worker.signals.finished.connect(self._on_update_finished)
        worker.signals.error.connect(self._on_error)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.log.connect(self._set_status)
        self.pool.start(worker)

    def _on_update_finished(self, _):
        self.needs_update = False
        self.updateBtn.setEnabled(False)
        self.updateBtn.setText("ゲームを更新")
        self.launchBtn.setEnabled(True)
        self._set_status("更新が完了しました！")
        self.progressBar.setValue(100)

    # ------------------------------------------------------------------
    # ランチャー自己更新
    # ------------------------------------------------------------------

    def _do_self_update(self):
        if not self.manifest:
            return
        url = self.manifest.get("launcher_download_url", "")
        if not url:
            QMessageBox.warning(self, "エラー", "ランチャーのダウンロードURLが見つかりません。")
            return

        reply = QMessageBox.question(
            self, "ランチャーを更新",
            "ランチャーを更新して再起動しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.launcherUpdateBtn.setEnabled(False)
        worker = SelfUpdateWorker(url)
        worker.signals.error.connect(self._on_error)
        worker.signals.log.connect(self._set_status)
        self.pool.start(worker)

    # ------------------------------------------------------------------
    # ゲーム起動
    # ------------------------------------------------------------------

    def _launch_game(self):
        exe = os.path.join(config.GAME_INSTALL_DIR, config.GAME_EXECUTABLE)
        if not os.path.exists(exe):
            QMessageBox.warning(self, "エラー", f"実行ファイルが見つかりません:\n{exe}")
            return

        if self.needs_update:
            reply = QMessageBox.question(
                self, "更新が残っています",
                "未適用の更新があります。このまま起動しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._set_status("ゲームを起動中...")
        try:
            if platform.system() == "Windows":
                os.startfile(exe)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", exe])
            else:
                subprocess.Popen([exe])
        except Exception as e:
            QMessageBox.critical(self, "起動エラー", str(e))
            return

        # ランチャーを最小化（必要に応じてコメントアウト）
        self.showMinimized()

    # ------------------------------------------------------------------
    # 共通ヘルパー
    # ------------------------------------------------------------------

    def _set_status(self, msg: str):
        self.statusLabel.setText(msg)

    def _on_progress(self, current: int, total: int, label: str):
        self.progressBar.setValue(current)
        self._set_status(f"ダウンロード中: {label}  {current}%")

    def _on_error(self, msg: str):
        self._set_status(f"エラー: {msg}")
        QMessageBox.critical(self, "エラー", msg)
        self.updateBtn.setEnabled(self.needs_update)
        self.launchBtn.setEnabled(True)


# =====================================================================
# エントリーポイント
# =====================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    # Windowsでタスクバーアイコンを正しく表示
    if platform.system() == "Windows":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"launcher.{config.GAME_TITLE}"
        )

    win = LauncherWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()