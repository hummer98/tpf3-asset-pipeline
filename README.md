# TPF3 Asset Pipeline

[日本語は下にあります](#日本語)

Build Transport Fever 3 models from Python and get them into a mod as
`.mdl` / `.msh` / `.mtl` / `.dds` without touching the mouse:

1. **Blender (headless)** builds the model from `assets/<name>/model.py`,
   exports one FBX per LOD plus textures, and renders preview PNGs.
2. **TF3 Model Editor** is driven over X11: the FBX is dropped onto its window
   via the XDND protocol and Save is clicked with a synthetic event. The real
   pointer never moves, so you can keep using the desktop.
3. The saved `.mdl` bounding box is checked against the size Blender built.

Made for working with an AI coding agent (Claude Code): it writes
`model.py`, looks at the preview PNGs, and runs the import, in a loop.

Full design notes, Model Editor findings and pitfalls (Japanese):
[docs/pipeline.md](docs/pipeline.md)

## Requirements

- Linux with an X server for the Model Editor (tested on KDE Plasma Wayland
  via XWayland). Windows is not supported.
- Transport Fever 3 (Steam, native Linux) with its Model Editor.
- Blender 5.x from Flathub, Python 3.10+.

```sh
flatpak install --user flathub org.blender.Blender
python3 -m venv .venv && .venv/bin/pip install python-xlib
```

The Model Editor only saves into mods under
`~/.local/share/Steam/userdata/<steam id>/3493540/local/staging_area/`.
Create a target mod there (`mod.json` with `modId` = folder name, plus
`_metadata/modinfo.json`); the default target is `tf3_asset_sandbox_1`.

## Usage

```sh
tools/blender.sh tools/build_asset.py -- bench   # out/bench/ (FBX + TGA), out/_preview/bench/ (PNG + report.json)
.venv/bin/python tools/me_import.py bench        # import into the Model Editor, save, verify (~10 s)
python3 tests/run.py                             # build + FBX checks + failure cases
python3 tests/test_me_import.py                  # me_import unit tests (no editor needed)
```

- Define an asset in `assets/<name>/model.py` with `build(lib)` (helpers in
  `tools/tf3lib.py`). One object per LOD, named after the asset; never add
  `_lodN` yourself (the Model Editor does).
- `me_import.py` rewrites the Model Editor settings file before launching it
  (Blender coordinate system on, overwrite meshes/materials/textures on,
  target mod) and leaves them that way.
- It refuses to run while a Model Editor is open, and always closes the one
  it started (unless `--keep-open`).
- The TF3 userdata folder is detected automatically; set `TF3_USERDATA` /
  `TF3_GAME_DIR` if you have several Steam accounts or a non-default install.
- Don't use `xdotool` clicks for this on Wayland: it can't move the pointer,
  so clicks land on whatever is under the cursor (e.g. the running game).

## License

MIT, see [LICENSE](LICENSE).

---

## 日本語

Python で書いた形から、Transport Fever 3 の MOD 用モデル (`.mdl` / `.msh` / `.mtl` / `.dds`)
までをマウス操作なしで作る仕組みです。

1. Blender をヘッドレスで動かし、`assets/<name>/model.py` から LOD ごとの FBX・テクスチャ・プレビュー画像を作る
2. TF3 の Model Editor を X11 で外から操作する (XDND でドロップ、合成クリックで保存)。実際のマウスは動かない
3. 保存された `.mdl` の寸法を Blender 側の寸法と照合する

Claude Code などの AI エージェントが、形を書く → プレビューを見る → 取り込む、を繰り返す用途を想定しています。
仕組み・Model Editor について調べたこと・ハマりどころは [docs/pipeline.md](docs/pipeline.md) にまとめています。
