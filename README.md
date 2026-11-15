# tf3_assets

Claude Code から Blender (flatpak, headless) と TF3 Model Editor を動かし、
TF3 用 3D アセットを手作業なしで `.mdl` まで仕上げる作業場。

**仕組み・仕様・ハマりどころは [docs/pipeline.md](docs/pipeline.md) を参照。**

```
tools/blender.sh tools/build_asset.py -- <asset>   # out/<asset>/ に FBX(LOD毎)+TGA、out/_preview/<asset>/ にプレビューPNG+report.json
.venv/bin/python tools/me_import.py <asset>         # Model Editor に自動取り込み → 保存 → bbox 検証 (~10秒)
python3 tests/run.py [asset ...]                    # ビルド → FBX 再読込で寸法/名前/UV/単位を検証
python3 tests/test_me_import.py                     # me_import の純関数テスト (エディタ不要)
```

- アセットは `assets/<name>/model.py` の `build(lib)` で定義 (lib = `tools/tf3lib.py`)。オブジェクト名に `_lodN` は付けない。
- 保存先は `userdata/.../local/staging_area/tf3_asset_sandbox_1/`。
- 初回: `flatpak install --user flathub org.blender.Blender` と `python3 -m venv .venv && .venv/bin/pip install python-xlib`。
- xdotool の mousemove/click は使わない (Wayland ではカーソル下のゲームに誤クリックする)。
