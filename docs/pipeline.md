# TF3 3D アセット自動パイプライン

Claude Code (または人間) が Python でモデルを書き、Transport Fever 3 の MOD 用モデル
(`.mdl` / `.msh` / `.mtl` / `.dds`) まで手作業なしで仕上げるための仕組み。

- 作成: 2026-11-15
- 動作確認環境: Bazzite (Fedora Atomic) / KDE Plasma Wayland / RTX 3090 / Blender 5.3 (flatpak) / TF3 Model Editor version 13

---

## 1. 全体像

```
assets/<name>/model.py          … 形を Python (bpy) で記述
        │
        │  tools/blender.sh tools/build_asset.py -- <name>      (Blender headless, ~10秒)
        ▼
out/<name>/                     … Model Editor に渡すものだけ
    <name>_lod0.fbx, <name>_lod1.fbx, <mat>_alb.tga
out/_preview/<name>/            … 人間/Claude が見るもの
    <name>_preview_{persp,front,side,top}.png, report.json (三角形数・寸法)
        │
        │  .venv/bin/python tools/me_import.py <name>           (Model Editor 自動操作, ~10秒)
        ▼
~/.local/share/Steam/userdata/<steam_user_id>/3493540/local/staging_area/tf3_asset_sandbox_1/content/<name>/
    <name>.mdl, msh/<name>_lodN.msh(.blob), mat/*.mtl, mat/tex/*.dds
```

ポイント:

- **Model Editor は FBX しか取り込めず、CLI も無い。** そこで Blender で FBX を作り、
  Model Editor は X11 プロトコルで外から操作する (§4)。
- **各段で検証する。** Blender 側は FBX を読み直して寸法・名前・UV を確認し (§3)、
  Model Editor 側は保存された `.mdl` の bbox を Blender の寸法と照合する (§4.5)。
- Claude はプレビュー PNG を画像として読めるので、ゲームを起動せずに形を確認しながら直せる。

## 2. 使い方

### 初回セットアップ

```sh
flatpak install --user flathub org.blender.Blender      # Blender 5.x
cd ~/tf3_assets
python3 -m venv .venv && .venv/bin/pip install python-xlib
```

保存先 MOD `staging_area/tf3_asset_sandbox_1/` (`mod.json` + `_metadata/modinfo.json`) は作成済み。
別の MOD に保存したいときは `staging_area/` 配下に同じ形で作り、`--mod` で指定する。

### 日常の流れ

```sh
# 1. 形を書く / 直す
$EDITOR assets/<name>/model.py

# 2. ビルドしてプレビューを見る
tools/blender.sh tools/build_asset.py -- <name>
#   → out/_preview/<name>/*.png を確認

# 3. Model Editor に取り込んで保存
.venv/bin/python tools/me_import.py <name>
#   → [me_import] {"bbox_matches_build": true, ...} なら成功 (exit 0)

# テスト
python3 tests/run.py               # 全アセットのビルド + FBX 検証 + 異常系
python3 tests/test_me_import.py    # me_import の純関数 (エディタ不要)
```

`me_import.py` の終了コード: 0 = 成功、1 = 途中で失敗 (メッセージ参照)、2 = 保存できたが寸法不一致。
`--keep-open` を付けると終了後もエディタを開いたままにする (目視確認用)。

## 3. Blender 側 (tools/build_asset.py, tools/tf3lib.py)

### アセットの書き方

`assets/<name>/model.py` に `build(lib)` を定義し、LOD ごとのオブジェクトとテクスチャを返す。

```python
def build(lib):
    img = lib.image("bench_wood_alb", (256, 256), fill_fn)    # 既定で不透明 (24bit)
    m_wood = lib.material("bench_wood", img)                  # マテリアル名がテクスチャ探索のキー
    lod0 = lib.join([lib.box(...), ...], "bench")             # オブジェクト名 = 要素名 (_lodN は付けない)
    lod1 = lib.join([...], "bench")
    return {"lods": {0: [lod0], 1: [lod1]},
            "textures": [(img, "bench_wood_alb.tga")]}
```

`tools/tf3lib.py` には `box` (キューブ投影 UV 付き)、`join`、`material`、`image` (手続き生成) がある。

### build_asset.py がやること

1. `build()` の戻り値を検査 (LOD0 必須、空の LOD 禁止、`_lodN` で終わる名前禁止)。違反したら何も書き出さずに止める。
2. `out/<name>/` と `out/_preview/<name>/` を作り直す。フォルダごと Model Editor に渡す運用だったため、古い LOD やテクスチャが残らないようにしている。
3. テクスチャを無圧縮 TGA で保存する。
4. LOD ごとに FBX を書き出す。このとき全 LOD のオブジェクト名とメッシュデータ名を一時的に `<name>` にそろえる (§6 の 3 と 4)。
5. 地面・太陽・カメラを足して、4 方向のプレビューを EEVEE で描画する。書き出しが先なので FBX には混入しない。
6. `report.json` に LOD ごとの三角形数・寸法を書く。

### FBX 書き出し設定

| 設定 | 値 | 理由 |
|---|---|---|
| 軸 | Blender 既定 (-Z forward, Y up) | Model Editor の "Use Blender Coordinate System" (= `importOptions.blenderMode`) と対になる |
| 単位 | `FBX_SCALE_UNITS` (UnitScaleFactor=100 = メートル) | 寸法 1:1 を Model Editor で確認済み |
| テクスチャパス | `path_mode=STRIP` | `RelativeFilename` がファイル名だけになる (`FileName` は Blender の仕様で絶対パスのまま) |

### テスト (tests/run.py, tests/check_fbx.py)

アセットを一時ディレクトリにビルドし、別の Blender で FBX を読み直して次を確かめる。

- LOD0 があること、FBX のファイル名、LOD1 の三角形が LOD0 より少ないこと
- オブジェクト名とメッシュデータ名が `<name>` であること、中身がメッシュだけであること
- FBX の `UnitScaleFactor` (バイナリから直接読む) が 100、頂点の範囲が report の寸法と一致すること
- `RelativeFilename` がファイル名だけであること、テクスチャ名の接尾辞が既知のものであること、アルベドが 24bit であること
- 異常系: LOD0 なし、空の LOD、`_lodN` 付きの名前で、ビルドが失敗し何も出力しないこと
- 古い出力が再ビルドで消えること

## 4. Model Editor 側 (tools/me_import.py, tools/xwin.py)

### 4.1 なぜ X11 で操作するのか

調べた結果:

- コマンドラインでの取り込みは無い。起動引数に FBX を渡しても無視される (実測)。
- 取り込みの入口はドラッグ＆ドロップ (SDL の `SDL_DROPFILE`) と UI だけ。保存のショートカットキーも無い。
- Model Editor (SDL2) は KDE Wayland 上で **XWayland** として動き、ウィンドウは `XdndAware` (version 5)。

そこで、X11 クライアントとして Model Editor のウィンドウにメッセージを直接送る。
**実際のマウスポインタは動かさないので、作業中も PC を使える。**

### 4.2 処理の流れ (me_import.py)

1. 前提を確認する: `out/<name>/<name>_lod0.fbx` があること、`report.json` が FBX より新しいこと、保存先 MOD があること、**Model Editor が動いていないこと** (`/proc/*/exe` で探す)。
2. 設定ファイル `~/.local/share/Transport Fever 3/model_editor_settings_v13.lua` を書き換える (§4.4)。一時ファイルに書いてから `os.replace` で置き換える。
3. Model Editor を別セッション (`start_new_session`) で起動し、出力を `~/tf3_assets/model_editor.log` に書く。
4. ログに `Set current mod: <mod>` が出るのを待つ。そのあと、自分が起動した PID (`_NET_WM_PID`) のウィンドウだけを探す。
5. XDND で `<name>_lod0.fbx` をドロップする (§4.3)。lod1 以降は Model Editor が同じフォルダから自動で拾う。
6. ログの `Validation: no errors` を待つ。エラーがあれば中止する。ウィンドウタイトルが `<mod>::/<name>/<name>.mdl` になったことも確認する。
7. 保存先のファイルの更新時刻を記録してから、Save ボタン (ウィンドウ内座標 74,14) に合成クリックを送る。`.mdl` とすべての `.msh` が書き直されるまで待つ。クリックが空振りした場合に備え、1 回だけ再試行する。
8. ファイルの書き込みが止まるのを待ってから `.mdl` の `bbMin`/`bbMax` を読み、report の寸法と照合する。
9. 成功・失敗にかかわらず、起動した Model Editor を終了する (`--keep-open` 指定時を除く)。

### 4.3 XDND ドロップ (xwin.drop_files)

XDND のドラッグ元として、次の順にやり取りする。

```
自分 (1x1 の見えないウィンドウ)          Model Editor
  XdndSelection の所有権を取る
  XdndEnter    (version, text/uri-list) ─▶
  XdndPosition (ウィンドウ中央, Copy)   ─▶
                                       ◀─ XdndStatus (受け入れ bit)
  XdndDrop                             ─▶
                                       ◀─ SelectionRequest (text/uri-list)
  file:///...fbx\r\n をプロパティに書き、SelectionNotify で返す
                                       ◀─ XdndFinished (受け入れ bit)
```

- 選択データの要求 (SelectionRequest) は 1 回のドロップにつき 1 回だけ来る。
- Model Editor のログには取り込みが 3 回分出るが、これはエディタ内部の動きで、ドロップは 1 回 (実測)。

### 4.4 固定する設定 (patch_settings)

| キー | 値 | 理由 |
|---|---|---|
| `importOptions.blenderMode` | `true` | UI の "Use Blender Coordinate System"。false だとログに "legacy axis system convention" と出る。`constructionImportOptions.blenderMode` は別物なので触らない |
| `importOptions.overwriteMeshes/Materials/Textures` | `true` | false だと再取り込み時に MOD 内の古い `.msh`/`.mtl`/`.dds` が使い回され (`Found mesh to reuse`)、形を直しても反映されない |
| `pathOptions.lastOpenedMod` | `{ "tf3_asset_sandbox_1", }` | 保存先 MOD。設定ファイルは**起動時にしか読まれない** |
| `pathOptions.userDataPath` | `.../3493540/local/` (末尾 `/` 必須) | 空だと起動時に "please add the path to your userdata directory" と出て止まる |

この設定は**元に戻さない**。手で Model Editor を使うときもこの設定のまま。
元の設定は `model_editor_settings_v13.lua.bak-20261115` に残してある。

### 4.5 保存結果の検証

- 合格条件: `.mdl` の bbox の各軸の長さが、report の LOD0 の寸法と ±1 cm 以内で一致すること。
- これで cm と m の取り違え (100 倍) や、Blender 座標系 OFF のとき起きる Y と Z の入れ替わりを検出できる。
- 実測では bench (1.8 × 0.52 × 0.85 m) が `bbMin {-0.9,-0.225,0}` / `bbMax {0.9,0.295,0.85}` になり、変換行列もほぼ単位行列だった。
- 長さを 2.0 m に変えて取り込み直すと ±1.0 になり、上書きが効いていることも確認した。

## 5. 調べて分かった TF3 / Model Editor の仕様

| 項目 | 内容 |
|---|---|
| 起動 | `cd "<TF3>/" && ./ModelEditor.sh` (相対パスで `model_editor/plugins` を読むため、cwd が必須) |
| 設定ファイル | `~/.local/share/Transport Fever 3/model_editor_settings_v13.lua` |
| ログ | 標準出力のみ (ファイルには残らない) |
| 保存先 MOD | ドロップダウンに出るのは `userdata/.../local/staging_area/` の MOD のみ (`local/mods/` は不可)。既定の `example_mod_1` は初回保存時に staging_area に自動作成される |
| 保存先 MOD の形式 | `mod.json` (`modId` = フォルダ名) + `_metadata/modinfo.json` + `content/` |
| 出力の配置 | `content/<要素名>/<要素名>.mdl`, `msh/<メッシュデータ名>_lodN.msh(.blob)`, `mat/<マテリアル名>.mtl`, `mat/tex/<テクスチャ>.dds` |
| LOD | 1 FBX = 1 LOD。`<name>_lod0.fbx` を渡すと `_lod1`, `_lod2` を同じフォルダから自動で探す |
| テクスチャ探索 | マテリアル名 + 接尾辞 (`_alb` `_nrm` `_mga` …) を FBX と同じフォルダ (と `lod0_bake/` などの兄弟フォルダ) で探す |
| テクスチャ形式 | 不透明アルベドは 24bit TGA にする。32bit だと BC3/DXT5 に圧縮され、"please use BC1/DXT1 for opaque textures" と警告される。24bit なら BC1_UNORM (DX10 ヘッダ) |
| プロセス名 | comm が "Main Thread" に変わる。`pgrep -x ModelEditor` では見つからないので `/proc/<pid>/exe` で探す |
| アセット名 | `-` は階層区切りとして扱われる (`a-b-name/` → `a/b/name/`) ※TF3 Wiki 記載 |

## 6. ハマりどころ (実際に踏んだもの)

1. **xdotool のクリックはゲームに入る。** Wayland では `xdotool mousemove` でポインタを動かせず、そのあとの `click` はカーソルの下にある別ウィンドウ (起動中の TF3) に届いた。**使わない。** 合成イベントをウィンドウに直接送る (`xwin.click`)。
2. **`pgrep -f model_editor/ModelEditor` は自分自身にも一致する。** `pkill -f` で自分のシェルを殺した。`/proc/*/exe` で探す。
3. **.msh のファイル名はメッシュデータ名から付く。** オブジェクト名ではない。初回は `Cube_lod0.msh` / `Cube.013_lod1.msh` になった。
4. **全 LOD を同名にすると Blender が `bench.001` に改名する。** そのため、書き出し中だけ他の LOD を一時名に退避する (`lod_names`)。
5. **flatpak 版 Blender の `/tmp` は別物。** 一時ディレクトリはリポジトリ配下 (`.test_out_*`) に作る。cwd も変わるので、スクリプトは絶対パスで渡す (`blender.sh` が `realpath` している)。
6. **同じセッションで、メッシュ名の変わったモデルを取り込み直すと 1 度 SIGSEGV した** (2026-11-15)。再現条件は未確定。対策として、me_import は毎回 Model Editor を新規起動して閉じる。
7. (予防、未確認) Model Editor は終了時に設定ファイルを書き戻すかもしれない。そのため、設定の書き換えは Model Editor が動いていないときだけ行う。

## 7. 制限と今後

- bbox の照合は軸ごとの長さだけ。Y と Z が同じ長さのモデルでは向きの誤りを見逃す。LOD1 は照合していない。
- Save ボタンの座標 (74,14) は UI スケール 1 が前提。
- XDND のタイムスタンプは `CurrentTime` (ICCCM では非推奨だが SDL2 では動く)。
- ゲーム内での見た目は未確認。staging_area の MOD がゲーム側で読み込まれるかも未確認。
- 今後の候補 (2026-11-15 の調査より): Blender MCP (Blender Lab 公式) で対話的にモデリングする、TRELLIS.2 (ComfyUI) で画像から 3D の下書きを作る、nanobanana-adc でテクスチャ素材を作る。

## 8. ファイル一覧

| パス | 役割 |
|---|---|
| `tools/blender.sh` | flatpak Blender をヘッドレスで起動するラッパー |
| `tools/build_asset.py` | ビルド本体 (Blender 内で実行) |
| `tools/tf3lib.py` | アセット記述用ヘルパー |
| `tools/me_import.py` | Model Editor の自動取り込み・保存・検証 |
| `tools/xwin.py` | X11 操作 (XDND ドロップ、合成クリック、ウィンドウ探索) |
| `assets/bench/model.py` | 動作確認用のベンチ |
| `tests/run.py`, `tests/check_fbx.py` | ビルドと FBX の検証 |
| `tests/test_me_import.py` | 設定書き換え・ログ判定・bbox 照合の単体テスト |
| `tests/fixtures/model_editor_settings_v13.lua` | 実物の設定ファイル (書き換えテスト用) |
| `model_editor.log` | 直近の Model Editor のログ (git 管理外) |
