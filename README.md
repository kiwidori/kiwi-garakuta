# きういのガラクタ置き場

Windows 11 x64向けの小さな無料ソフトを公開しています。人気のコマンドラインツールを、画面から使えるようにした非公式のGUIです。インストーラーはなく、ZIPを展開して起動できます。

**[公開サイトでソフトを見る](https://kiwi-garakuta.pages.dev/)** · [GitHub Releasesからダウンロード](https://github.com/kiwidori/kiwi-garakuta/releases)

## 公開中のソフト

| ソフト | できること | 元になったツール |
| --- | --- | --- |
| [きうい検索](https://kiwi-garakuta.pages.dev/tools/kiwi-search/) | フォルダー内の文章を検索し、該当する行を表示 | [ripgrep](https://github.com/BurntSushi/ripgrep) |
| [きういファイル探し](https://kiwi-garakuta.pages.dev/tools/kiwi-find/) | 名前や拡張子からファイルを探す | [fd](https://github.com/sharkdp/fd) |
| [きうい容量ビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-disk/) | 容量の大きいファイルやフォルダーを確認する | [dust](https://github.com/bootandy/dust) |
| [きういJSON](https://kiwi-garakuta.pages.dev/tools/kiwi-json/) | JSONから必要なデータを取り出し、結果を保存する | [jq](https://github.com/jqlang/jq) |
| [きういコードビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-code/) | コードやテキストを色付き・行番号付きで閲覧する | [bat](https://github.com/sharkdp/bat) |
| [きういPC情報](https://kiwi-garakuta.pages.dev/tools/kiwi-system/) | OS・CPU・GPU・メモリなどPCの概要を確認する | [fastfetch](https://github.com/fastfetch-cli/fastfetch) |
| [きうい秘密チェック](https://kiwi-garakuta.pages.dev/tools/kiwi-secrets/) | 公開前のフォルダーからAPIキーなどの機密情報候補を探す | [Gitleaks](https://github.com/gitleaks/gitleaks) |
| [きうい正規表現](https://kiwi-garakuta.pages.dev/tools/kiwi-regex/) | 文字列の例から正規表現を作る | [grex](https://github.com/pemistahl/grex) |
| [きういHTTPビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-http/) | HTTPの応答ヘッダー・本文を確認する | [xh](https://github.com/ducaale/xh) |
| [きういPNG圧縮](https://kiwi-garakuta.pages.dev/tools/kiwi-png/) | PNGを圧縮して別ファイルへ保存する | [oxipng](https://github.com/oxipng/oxipng) |
| [きういYAML](https://kiwi-garakuta.pages.dev/tools/kiwi-yaml/) | YAMLを整形し、JSONへ変換する | [yq](https://github.com/mikefarah/yq) |
| [きういハッシュ](https://kiwi-garakuta.pages.dev/tools/kiwi-hash/) | BLAKE3ハッシュを計算・照合する | [b3sum / BLAKE3](https://github.com/BLAKE3-team/BLAKE3) |
| [きうい色変換](https://kiwi-garakuta.pages.dev/tools/kiwi-color/) | HEX・RGB・HSLを変換して色見本を確認する | [pastel](https://github.com/sharkdp/pastel) |
| [きうい文字絵](https://kiwi-garakuta.pages.dev/tools/kiwi-ascii/) | 静止画像をASCII・点字文字の文字絵に変換する | [ascii-image-converter](https://github.com/TheZoraiz/ascii-image-converter) |
| [きうい空き容量](https://kiwi-garakuta.pages.dev/tools/kiwi-space/) | ドライブの容量を一覧表示・CSV保存する | [duf](https://github.com/muesli/duf) |
| [きうい比較](https://kiwi-garakuta.pages.dev/tools/kiwi-diff/) | テキスト・コードの差分を表示・保存する | [difftastic](https://github.com/Wilfred/difftastic) |
| [きういコード集計](https://kiwi-garakuta.pages.dev/tools/kiwi-count/) | コードの行数・複雑度・Git履歴を集計し、HTMLレポートを保存する | [scc](https://github.com/boyter/scc) |
| [きういシェル整形](https://kiwi-garakuta.pages.dev/tools/kiwi-shell/) | シェルの整形・差分・AST変換と一括整形を行う | [shfmt](https://github.com/mvdan/sh) |
| [きういWeb圧縮](https://kiwi-garakuta.pages.dev/tools/kiwi-minify/) | Webファイルの圧縮・連結・フォルダー処理を行う | [minify](https://github.com/tdewolff/minify) |
| [きういデータ変換](https://kiwi-garakuta.pages.dev/tools/kiwi-data/) | 8形式のデータ変換、式による抽出・並べ替え・集計を行う | [dasel](https://github.com/TomWright/dasel) |

| [きういMarkdown](https://kiwi-garakuta.pages.dev/tools/kiwi-markdown/) | Markdown・URL・READMEを装飾付きで表示し、テキストを保存する | [Glow](https://github.com/charmbracelet/glow) |

| [きうい置換](https://kiwi-garakuta.pages.dev/tools/kiwi-replace/) | 文字列・正規表現でテキストと複数ファイルを置換して保存する | [sd](https://github.com/chmln/sd) |

| [きういバイト表示](https://kiwi-garakuta.pages.dev/tools/kiwi-bytes/) | バイナリを16進数・文字表で表示し、テキストやC配列に保存する | [hexyl](https://github.com/sharkdp/hexyl) |

各ソフトの詳細ページに、使い方、実際の画面、制限事項、ZIPのダウンロード先を掲載しています。ZIPには元ツールのライセンス文書を同梱しています。

## 使い方

1. 上の一覧からソフトの詳細ページを開き、ZIPをダウンロードします。
2. ZIPを任意のフォルダーへ展開します。
3. 中の `KiwiSearch.exe`、`KiwiFind.exe`、`KiwiDisk.exe` など、選んだソフトの実行ファイルを起動します。ファイル名と機能は各ソフトの詳細ページとZIP内のREADMEに記載しています。

各ソフトはWindows 11 x64で動作確認しています。現時点の実行ファイルにはコード署名がありません。配布元とZIPの内容を確認してから使用してください。

## ソースコードとライセンス

GUIのソースコードは [`apps/`](apps/) にあります。このリポジトリのコードは [MITライセンス](LICENSE) で公開しています。元ツールにはそれぞれのライセンスが適用されます。各ソフトの詳細ページと配布ZIP内のライセンス文書を参照してください。

これらのGUIは元ツールの開発者による公式製品ではありません。

## 開発について

各ソフトの「詳細機能」画面では、同梱CLIの追加オプションを選択し、値・ファイル・標準入力を指定して実行できます。通常画面との違いと制限は [上流ツールとの機能差分](docs/upstream-feature-audit.md) を参照してください。共通画面のコードは [`apps/common/`](apps/common/) にあります。

サイトは `catalog.json` をもとに `python site/build.py` で生成します。ソフトは `apps/` 内の各フォルダーにあり、`verify.py` で主要機能、`smoke_zip.py` で完成ZIPの起動と同梱物を確認できます。配布ビルドは `build.py` を参照してください。

不具合や質問は [@kiwi_dori のDM](https://x.com/kiwi_dori) へお寄せください。開発を支援したい場合は、各ソフトの詳細ページにPayPalリンクがあります。
