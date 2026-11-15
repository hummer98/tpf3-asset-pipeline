# Contributing

[日本語は下にあります](#日本語)

Thanks for your interest. This is a small personal tool, so issues and pull
requests are welcome but reviewed on a best-effort basis.

How the pipeline works and why each step exists is in
[docs/pipeline.md](docs/pipeline.md) (Japanese). Please skim §4–§6 before
changing `tools/me_import.py` or `tools/xwin.py`.

## Layout

```
assets/<name>/model.py   # one asset = build(lib) returning LOD objects + textures
tools/blender.sh         # runs flatpak Blender headless with a script
tools/build_asset.py     # build: validate, export FBX per LOD, TGA, previews, report.json
tools/tf3lib.py          # helpers for model.py (box, join, material, image)
tools/me_import.py       # drives the TF3 Model Editor: settings, launch, drop, save, verify
tools/xwin.py            # X11 plumbing: XDND drop, synthetic click, window lookup
tests/run.py             # builds every asset in Blender and checks the FBX output
tests/check_fbx.py       # (runs inside Blender) re-imports FBX for run.py
tests/test_me_import.py  # unit tests for me_import's pure helpers
tests/fixtures/          # real Model Editor settings file used by the tests
docs/pipeline.md         # design notes, Model Editor findings, pitfalls
```

`out/`, `.venv/`, `.test_out_*/` and `model_editor.log` are generated and
ignored.

## Setup

```sh
git clone https://github.com/hummer98/tpf3-asset-pipeline.git
cd tpf3-asset-pipeline
flatpak install --user flathub org.blender.Blender
python3 -m venv .venv && .venv/bin/pip install python-xlib
```

## Tests

Run before every commit:

```sh
python3 tests/test_me_import.py   # seconds, no Blender / editor needed
python3 tests/run.py              # ~20 s, launches Blender headless; includes failure cases
```

`python3 tests/run.py <asset>` checks a single asset but skips the failure-case
and stale-output tests, so run it without arguments before you push.

`tools/me_import.py` opens a real Model Editor window and has no automated
test. If you touch it, `tools/xwin.py` or the settings handling, run it by
hand and paste the `[me_import] {...}` line in the pull request:

```sh
tools/blender.sh tools/build_asset.py -- bench
.venv/bin/python tools/me_import.py bench   # expect "bbox_matches_build": true, exit 0
```

There is no CI (the tests need Blender and the Model Editor needs TF3 and an
X server).

## Making changes

- **Bug fix → add a test that fails without the fix.** New behaviour → a
  representative case plus edge cases (missing / empty / wrong names, etc.).
- Keep pure logic (parsing, settings patching, decisions) in functions that
  `tests/test_me_import.py` can call without an editor.
- Comments explain *why*, not *what*. Commit messages say why the change is
  needed; the diff shows what changed.
- Behaviour-visible changes update `README.md` and `docs/pipeline.md` in the
  same commit.
- New Model Editor or TF3 findings go into `docs/pipeline.md` §5/§6 with how
  you confirmed them (log line, file contents, experiment).

### Adding an asset

- One object per LOD, named exactly like the asset folder; never add `_lodN`.
- Name materials after their textures (`<material>_alb.tga`, `_nrm`, `_mga`, …).
- Opaque albedo stays 24-bit (`lib.image` default); pass `alpha=True` only
  when the texture really needs alpha.
- `python3 tests/run.py` must pass with the new asset included.

### Safety rules for editor automation

- **Never use `xdotool mousemove` / `click`.** On Wayland it can't move the
  pointer, so the click lands on whatever window is under the cursor (it hit
  a running game once). Send events to the editor window via `tools/xwin.py`.
- Only send input to the window whose `_NET_WM_PID` is the editor process
  you started.
- The editor's process name is "Main Thread"; find it via `/proc/<pid>/exe`,
  not `pgrep -x` (and `pgrep -f`/`pkill -f` will match your own shell).
- Change the settings file only while no editor is running.

## Reporting issues

Please include your distro / desktop (Wayland or X11), Blender version, the
command you ran and its output. If you attach `model_editor.log`, remove or
mask your home path and Steam user id first (they appear in file paths).

## License

By contributing you agree that your contribution is licensed under the
[MIT License](LICENSE).

---

## 日本語

個人用の小さなツールなので、Issue と PR は歓迎しますが、対応はできる範囲になります。
仕組みと各工程の理由は [docs/pipeline.md](docs/pipeline.md) にあります。
`tools/me_import.py` と `tools/xwin.py` を触る前に §4〜§6 に目を通してください。

**コミット前に必ず**

```sh
python3 tests/test_me_import.py   # 数秒、Blender もエディタも不要
python3 tests/run.py              # 約 20 秒、Blender を起動。引数なしで異常系も実行
```

- `tools/me_import.py` は本物の Model Editor を開くので自動テストがありません。
  ここ・`tools/xwin.py`・設定の書き換えを変えたら、手で実行して `[me_import] {...}` の行を PR に貼ってください。
- CI はありません (Blender と TF3、X サーバーが必要なため)。

**変更のルール**

- バグ修正には、修正前に失敗する回帰テストを付ける。新機能には代表ケースとエッジケースのテストを付ける。
- 判定や解析などの処理は、エディタなしでテストできる関数に切り出す。
- コメントは「何」ではなく「なぜ」を書く。コミットメッセージには「なぜ必要か」を書く。
- 挙動が変わる変更は、同じコミットで `README.md` と `docs/pipeline.md` も更新する。
- Model Editor / TF3 について新しく分かったことは、確かめ方 (ログ・ファイルの中身・実験) と一緒に `docs/pipeline.md` §5/§6 に書く。

**アセットを追加するとき**

- 1 LOD = 1 オブジェクト、名前はアセットのフォルダ名と同じにする。`_lodN` は付けない。
- マテリアル名はテクスチャ名に合わせる (`<マテリアル名>_alb.tga` など)。
- 不透明なアルベドは 24bit のまま。アルファが本当に必要なときだけ `alpha=True` を付ける。

**エディタ自動操作の安全ルール**

- `xdotool mousemove` / `click` は使わない。Wayland ではポインタを動かせず、カーソルの下のウィンドウ (起動中のゲームなど) にクリックが入る。
- 入力を送るのは、自分が起動したエディタのプロセスのウィンドウ (`_NET_WM_PID`) だけにする。
- エディタのプロセス名は "Main Thread" なので `/proc/<pid>/exe` で探す (`pgrep -f` / `pkill -f` は自分のシェルにも一致する)。
- 設定ファイルは、エディタが動いていないときだけ書き換える。

**不具合の報告**: ディストリビューション / デスクトップ (Wayland か X11)、Blender のバージョン、実行したコマンドと出力を書いてください。
`model_editor.log` を添付する場合は、ホームのパスと Steam ユーザー ID を伏せてください (ファイルパスに含まれます)。
