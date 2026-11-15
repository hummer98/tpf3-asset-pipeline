# tf3_assets

Claude Code から Blender (flatpak, headless) を動かして TF3 用 3D アセットを作る作業場。

```
tools/blender.sh tools/build_asset.py -- <asset>   # out/<asset>/ に FBX(LOD毎) + TGA、out/_preview/<asset>/ にプレビューPNG + report.json
python3 tests/run.py [asset ...]                    # ビルド → FBX 再読込で寸法/UV/マテリアルを検証
python3 tests/test_me_import.py                     # me_import の純関数テスト (エディタ不要)
.venv/bin/python tools/me_import.py <asset>         # Model Editor に自動取り込み + 保存 + bbox 検証 (~10秒)
```

## Model Editor 自動化 (tools/me_import.py, tools/xwin.py)

Model Editor は CLI も argv 取り込みもないので、XWayland 上のウィンドウに X11 で直接話す:
- 取り込み: XDND プロトコルで `<asset>_lod0.fbx` をドロップ (マウス不使用)
- 保存: ツールバーの Save (74,14) に合成クリック (SDL は send_event を受け付ける)
- 設定 `~/.local/share/Transport Fever 3/model_editor_settings_v13.lua` を起動前に固定 (元に戻さない。手動で使うときもこの設定のまま):
  `importOptions.blenderMode=true` (= Use Blender Coordinate System), `overwriteMeshes/Materials/Textures=true`
  (false だと再取り込みで MOD 内の古い .msh/.mtl/.dds が使い回される), `lastOpenedMod`, `userDataPath`
- 毎回エディタを新規起動して終了する。既にエディタが動いていたら中止 (設定は起動時しか読まれないため)。
- 送信先は自分が起動したプロセスのウィンドウ (_NET_WM_PID) に限定。
- 保存先 MOD は `local/staging_area/` 配下のみ選べる (既定 `tf3_asset_sandbox_1`)
- 保存後の `.mdl` bbox を Blender 側 report の寸法と照合 (cm/m 取り違え・Y-up を検出)

注意:
- xdotool の mousemove/click は Wayland ではポインタを動かせず、カーソル下 (ゲーム等) に誤クリックする。使わない。
- エディタのプロセス名 (comm) は "Main Thread" なので `pgrep -x ModelEditor` では見つからない。
- 同一セッションでメッシュ名の変わったモデルを取り込み直したとき 1 度 SIGSEGV (2026-11-15)。
- bbox 照合は軸ごとの寸法のみ (Y/Z が同寸のモデルでは Y-up 誤りを見逃す)、LOD1 は未照合。
- Save ボタン座標 (74,14) は UI スケール 1 前提。
- 環境: `python3 -m venv .venv && .venv/bin/pip install python-xlib`

- アセットは `assets/<name>/model.py` の `build(lib)` で定義 (lib = tools/tf3lib.py)。
- Model Editor への取り込みは手作業 (CLI なし): `out/<name>/` をフォルダごとドロップし、
  "Use Blender Coordinate System" を ON。テクスチャはマテリアル名 + `_alb` 等の接尾辞で自動対応。
- `out/<asset>/` はビルド毎に作り直す (古い LOD/テクスチャを残さない)。オブジェクト名に `_lodN` は付けない (Model Editor が付ける)。
- アセット名に `-` を使うと Model Editor で階層区切り扱い (`a-b-name/` → `a/b/name/`)。
- 確認済み (Model Editor): 寸法 1:1、Z-up、TGA(24bit)→DDS BC1。未確認: ゲーム内での見た目。
