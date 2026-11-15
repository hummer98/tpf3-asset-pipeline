# tf3_assets

Claude Code から Blender (flatpak, headless) を動かして TF3 用 3D アセットを作る作業場。

```
tools/blender.sh tools/build_asset.py -- <asset>   # out/<asset>/ に FBX(LOD毎) + TGA + プレビューPNG + report.json
python3 tests/run.py [asset ...]                    # ビルド → FBX 再読込で寸法/UV/マテリアルを検証
```

- アセットは `assets/<name>/model.py` の `build(lib)` で定義 (lib = tools/tf3lib.py)。
- Model Editor への取り込みは手作業 (CLI なし): `out/<name>/` をフォルダごとドロップし、
  "Use Blender Coordinate System" を ON。テクスチャはマテリアル名 + `_alb` 等の接尾辞で自動対応。
