# きういのガラクタ置き場

Windows 11 x64向けの小さな無料ソフトを公開しています。人気のコマンドラインツールを、画面から使えるようにした非公式のGUIです。インストーラーはなく、ZIPを展開して起動できます。

**[公開サイトでソフトを見る](https://kiwi-garakuta.pages.dev/)** · [GitHub Releasesからダウンロード](https://github.com/kiwidori/kiwi-garakuta/releases)

## 公開中のソフト

| ソフト | できること | 元になったツール |
| --- | --- | --- |
| [きういYAML作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-yaml-workbench/) | YAMLの変換・編集・整形とGitHub Actionsの検査を行う | [yq](https://github.com/mikefarah/yq)・[yamlfmt](https://github.com/google/yamlfmt)・[actionlint](https://github.com/rhysd/actionlint) |
| [きうい容量作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-capacity-workbench/) | ドライブの空き容量からフォルダーの内訳・再解析へ進む | [dust](https://github.com/bootandy/dust)・[duf](https://github.com/muesli/duf) |
| [きういテキスト作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-text-workbench/) | 例から作った正規表現でテキストやファイルを置換する | [grex](https://github.com/pemistahl/grex)・[sd](https://github.com/chmln/sd) |
| [きういYouTube字幕](https://kiwi-garakuta.pages.dev/tools/kiwi-youtube-captions/) | 字幕の閲覧・検索・翻訳とTXT/SRTなどへの保存 | [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) |
| [きうい検索作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-search-workbench/) | 名前で絞ったファイルから内容を検索する | [fd](https://github.com/sharkdp/fd)・[ripgrep](https://github.com/BurntSushi/ripgrep) |
| [きういJSON](https://kiwi-garakuta.pages.dev/tools/kiwi-json/) | JSONから必要なデータを取り出し、結果を保存する | [jq](https://github.com/jqlang/jq) |
| [きういJSON作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-json-workbench/) | JSONのツリー閲覧・式変換・パス一覧と復元を同じ入力で行う | [fx](https://github.com/antonmedv/fx)・[gojq](https://github.com/itchyny/gojq)・[gron](https://github.com/tomnomnom/gron) |
| [きういコードビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-code/) | コードやテキストを色付き・行番号付きで閲覧する | [bat](https://github.com/sharkdp/bat) |
| [きういPC情報](https://kiwi-garakuta.pages.dev/tools/kiwi-system/) | OS・CPU・GPU・メモリなどPCの概要を確認する | [fastfetch](https://github.com/fastfetch-cli/fastfetch) |
| [きうい秘密チェック](https://kiwi-garakuta.pages.dev/tools/kiwi-secrets/) | 公開前のフォルダーからAPIキーなどの機密情報候補を探す | [Gitleaks](https://github.com/gitleaks/gitleaks) |
| [きういHTTPビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-http/) | HTTPの応答ヘッダー・本文を確認する | [xh](https://github.com/ducaale/xh) |
| [きういPNG圧縮](https://kiwi-garakuta.pages.dev/tools/kiwi-png/) | PNGを圧縮して別ファイルへ保存する | [oxipng](https://github.com/oxipng/oxipng) |
| [きういハッシュ](https://kiwi-garakuta.pages.dev/tools/kiwi-hash/) | BLAKE3ハッシュを計算・照合する | [b3sum / BLAKE3](https://github.com/BLAKE3-team/BLAKE3) |
| [きうい色変換](https://kiwi-garakuta.pages.dev/tools/kiwi-color/) | HEX・RGB・HSLを変換して色見本を確認する | [pastel](https://github.com/sharkdp/pastel) |
| [きうい文字絵](https://kiwi-garakuta.pages.dev/tools/kiwi-ascii/) | 静止画像をASCII・点字文字の文字絵に変換する | [ascii-image-converter](https://github.com/TheZoraiz/ascii-image-converter) |
| [きうい比較](https://kiwi-garakuta.pages.dev/tools/kiwi-diff/) | テキスト・コードの差分を表示・保存する | [difftastic](https://github.com/Wilfred/difftastic) |
| [きういコード集計](https://kiwi-garakuta.pages.dev/tools/kiwi-count/) | コードの行数・複雑度・Git履歴を集計し、HTMLレポートを保存する | [scc](https://github.com/boyter/scc) |
| [きういシェル整形](https://kiwi-garakuta.pages.dev/tools/kiwi-shell/) | シェルの整形・差分・AST変換と一括整形を行う | [shfmt](https://github.com/mvdan/sh) |
| [きういWeb圧縮](https://kiwi-garakuta.pages.dev/tools/kiwi-minify/) | Webファイルの圧縮・連結・フォルダー処理を行う | [minify](https://github.com/tdewolff/minify) |
| [きういデータ変換](https://kiwi-garakuta.pages.dev/tools/kiwi-data/) | 8形式のデータ変換、式による抽出・並べ替え・集計を行う | [dasel](https://github.com/TomWright/dasel) |
| [きういMarkdown](https://kiwi-garakuta.pages.dev/tools/kiwi-markdown/) | Markdown・URL・READMEを装飾付きで表示し、テキストを保存する | [Glow](https://github.com/charmbracelet/glow) |
| [きういバイト表示](https://kiwi-garakuta.pages.dev/tools/kiwi-bytes/) | バイナリを16進数・文字表で表示し、テキストやC配列に保存する | [hexyl](https://github.com/sharkdp/hexyl) |
| [きうい単位計算](https://kiwi-garakuta.pages.dev/tools/kiwi-calc/) | 単位変換と単位付きの科学計算、プログラム・スクリプト実行 | [Numbat](https://github.com/sharkdp/numbat) |
| [きういコード資料](https://kiwi-garakuta.pages.dev/tools/kiwi-prompt/) | コード・Git情報をLLM向け資料にまとめ、トークン分布を確認する | [code2prompt](https://github.com/mufeedvh/code2prompt) |

各ソフトの詳細ページに、使い方、実際の画面、制限事項、ZIPのダウンロード先を掲載しています。ZIPには元ツールのライセンス文書を同梱しています。

## 使い方

1. 上の一覧からソフトの詳細ページを開き、ZIPをダウンロードします。
2. ZIPを任意のフォルダーへ展開します。
3. 中の `KiwiSearchWorkbench.exe`、`KiwiDisk.exe` など、選んだソフトの実行ファイルを起動します。ファイル名と機能は各ソフトの詳細ページとZIP内のREADMEに記載しています。

各ソフトはWindows 11 x64で動作確認しています。現時点の実行ファイルにはコード署名がありません。配布元とZIPの内容を確認してから使用してください。

### 追加オプションを使う

各ソフトのメニューから「詳細機能」を開くと、元ツールの追加オプションを指定できます。対応する機能や通常画面との違い、制限は [各ソフトの機能と制限](docs/upstream-feature-audit.md) を参照してください。

## ソースコードとライセンス

GUIのソースコードは [`apps/`](apps/) にあります。このリポジトリのコードは [MITライセンス](LICENSE) で公開しています。元ツールにはそれぞれのライセンスが適用されます。各ソフトの詳細ページと配布ZIP内のライセンス文書を参照してください。

これらのGUIは元ツールの開発者による公式製品ではありません。

## 問い合わせ

不具合や質問は [@kiwi_dori のDM](https://x.com/kiwi_dori) へお寄せください。お問い合わせの際は、ソフト名・バージョンと、問題が起きた操作やエラーメッセージをお知らせください。画像やログを添える場合は、個人情報を取り除いてください。

## 開発を支援する

ソフトは無料で利用できます。役に立った場合は、各ソフトの詳細ページにあるPayPalリンクから開発を支援できます。
