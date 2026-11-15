# tf3_assets

Claude Code から Blender (flatpak, headless) を動かして TF3 用 3D アセットを作る作業場。

```
tools/blender.sh tools/build_asset.py -- <asset>   # out/<asset>/ に FBX(LOD毎) + TGA、out/_preview/<asset>/ にプレビューPNG + report.json
python3 tests/run.py [asset ...]                    # ビルド → FBX 再読込で寸法/UV/マテリアルを検証
```

- アセットは `assets/<name>/model.py` の `build(lib)` で定義 (lib = tools/tf3lib.py)。
- Model Editor への取り込みは手作業 (CLI なし): `out/<name>/` をフォルダごとドロップし、
  "Use Blender Coordinate System" を ON。テクスチャはマテリアル名 + `_alb` 等の接尾辞で自動対応。
- `out/<asset>/` はビルド毎に作り直す (古い LOD/テクスチャを残さない)。オブジェクト名に `_lodN` は付けない (Model Editor が付ける)。
- アセット名に `-` を使うと Model Editor で階層区切り扱い (`a-b-name/` → `a/b/name/`)。
- 未確認 (初回ゲーム内取り込みで確認): 寸法 1:1、向き、TGA→DDS 変換。
