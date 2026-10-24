# BeamerPlus

LaTeX / Beamer 等の PDF スライドによるプレゼンテーションを快適に行うための、デュアルスクリーン対応・発表者ビューツールです。

---

## 主な機能

- **デュアルスクリーン対応**:
  - プロジェクタ/外部ディスプレイに自動全画面表示する「Viewer」と、手元でノートやタイマーを確認できる「発表者ビュー」が完全同期。
- **手書き描画 & テキスト書き込み**:
  - キーボード入力による任意位置へのテキスト注釈書き込み（フォントサイズ・文字色変更、Return確定、Escキャンセル）。
  - レーザーポインタ、手書きペン、蛍光ペン（半透明ハイライト）。
  - Wacom や液晶タブレットの筆圧検知・ホバーインジケータ・ペン尻消しゴム自動認識。
  - 水平・垂直 ±5度 スナップ対応の「直線描画」モード。
  - 手書きストロークとテキストを時系列で正確に取り消せる統合 Undo 機能。
- **消しゴム機能**:
  - なぞった部分のみを切り取る「通常消しゴム」と、ストローク全体を消去する「オブジェクト消しゴム」のワンクリック切り替え。
- **Markdown スライドノート**:
  - ページごとに Markdown 形式で発表原稿やメモを記述・プレビュー可能。
  - スライド PDF と同じディレクトリに JSON ファイルとして自動保存。
- **プレゼンテーションタイマー & 画面暗転**:
  - 経過時間タイマー（開始・一時停止・リセット）。
  - `B` キーまたはボタンで瞬時にプロジェクタ画面をブラックアウトする暗転機能。

---

## インストール方法

### pipx を使う場合（推奨）
Python アプリケーションをシステム環境から隔離してグローバルコマンドとしてインストールできます。

<!-- #### 1. PyPI からインストール（公式リリース時）
```bash
pipx install beamerplus
``` -->

#### GitHub から直接インストール
```bash
pipx install git+https://github.com/HaruhiroObora/BeamerPlus.git
```

### pip を使う場合
```bash
pip install git+https://github.com/HaruhiroObora/BeamerPlus.git
```

---

## 使い方

ターミナルからスライド PDF を指定して起動します：

```bash
beamerplus slides.pdf
```

引数を省略して起動し、ツールバーの「📁 開く」から PDF を選択することもできます：

```bash
beamerplus
```

### 主なショートカットキー
| キー | 操作 |
| :--- | :--- |
| `◀` / `▶` / `PageUp` / `PageDown` | ページ送り / 戻し |
| `B` | 画面の暗転（ブラックアウト）のトグル |
| `F5` | プロジェクタ画面（Viewer）の表示 / 非表示 |
| `F11` | プロジェクタ画面の全画面表示切替 |
| `Ctrl + N` (`Cmd + N`) | ノートパネルの表示 / 非表示 |
| `Ctrl + T` (`Cmd + T`) | 下部スライド一覧サムネイルの表示 / 非表示 |

---

## デスクトップショートカットの追加

ターミナルを開かずにアイコンのダブルクリックや、PDF ファイルのドラッグ＆ドロップから起動できるように、各 OS でデスクトップショートカットを作成できます。

### 🐧 Linux (Ubuntu, Debian, Fedora, Arch 等)

デスクトップエントリーファイル（`.desktop`）を作成することで、アプリメニューやデスクトップからワンクリックで起動できるようになります。

1. **エントリーファイルの作成**:
   ターミナルで以下のコマンドを実行します：
   ```bash
   mkdir -p ~/.local/share/applications
   cat << 'EOF' > ~/.local/share/applications/beamerplus.desktop
   [Desktop Entry]
   Version=1.0
   Type=Application
   Name=BeamerPlus
   Comment=LaTeX/Beamer PDF Presenter View
   Exec=beamerplus %f
   Icon=x-office-presentation
   Terminal=false
   Categories=Office;Presentation;
   MimeType=application/pdf;
   EOF
   ```
2. **デスクトップにアイコンを置く場合**:
   ```bash
   cp ~/.local/share/applications/beamerplus.desktop ~/Desktop/
   chmod +x ~/Desktop/beamerplus.desktop
   ```
   ※ Ubuntu (GNOME) の場合、デスクトップに置いたアイコンを右クリックし、「**起動を許可する (Allow Launching)**」を選択してください。
3. **右クリックから開く**:
   PDF ファイルを右クリック →「別のアプリケーションで開く」から `BeamerPlus` を選択して開くことも可能になります。

---

### 🍎 macOS

macOS 標準アプリ「Automator」を使って、PDF のドラッグ＆ドロップにも対応したアプリ（`.app`）を作成できます。

1. **Automator を起動**:
   - `Spotlight`（`Cmd + Space`）で「Automator」と入力して開きます。
2. **書類の種類を選択**:
   - 「新規書類」から「**アプリケーション**」を選択して「選択」をクリックします。
3. **シェルスクリプトを追加**:
   - 左側ライブラリの「ユーティリティ」から「**シェルスクリプトを実行**」を右側のワークフロー領域にドラッグ＆ドロップします。
   - **入力の引き渡し方法** を「**引数として**」に変更します。
   - スクリプト入力欄に以下を記述します：
     ```bash
     export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
     if [ $# -eq 0 ]; then
         beamerplus
     else
         beamerplus "$1"
     fi
     ```
4. **保存**:
   - `Cmd + S` を押し、名前を `BeamerPlus`、保存先を「アプリケーション」フォルダ（またはデスクトップ）にして保存します。
5. **使い方**:
   - アイコンをダブルクリックで起動できるほか、PDF ファイルをこのアイコンに **ドラッグ＆ドロップ** して直接開くこともできます。

---

### 🪟 Windows (Windows 10 / 11)

Windows 標準のショートカット機能で簡単に作成できます。

1. **ショートカット作成ウィザード**:
   - デスクトップの何もない場所で **右クリック →「新規作成」→「ショートカット」** を選択します。
2. **コマンドの指定**:
   - 「項目の場所を入力してください」に以下を入力して「次へ」をクリックします：
     - **pipx でインストールした場合**:
       ```text
       %USERPROFILE%\.local\bin\beamerplus.exe
       ```
     - **pip でインストールした場合**:
       ```text
       python -m beamerplus.main
       ```
3. **名前の指定**:
   - ショートカットの名前を「`BeamerPlus`」にして「完了」をクリックします。
4. **アイコンの変更（お好みで）**:
   - 作成されたショートカットを右クリック →「プロパティ」を開きます。
   - 「ショートカット」タブの「アイコンの変更」から、お好みのアイコンを選択して「OK」をクリックします。
5. **便利な使い方**:
   - スライド PDF ファイルをこのデスクトップアイコン上に **ドラッグ＆ドロップ** すると、該当スライドを直接開いて起動できます。

---

## ライセンス
MIT License
