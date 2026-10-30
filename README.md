# きういのガラクタ置き場

Windows 11 x64向けの小さな無料ソフトを公開しています。人気のコマンドラインツールを、画面から使えるようにした非公式のGUIです。インストーラーはなく、ZIPを展開して起動できます。

**[公開サイトでソフトを見る](https://kiwi-garakuta.pages.dev/)** · [GitHub Releasesからダウンロード](https://github.com/kiwidori/kiwi-garakuta/releases)

## 公開中のソフト

| ソフト | できること | 元になったツール |
| --- | --- | --- |
| [きうい読み取り・読み上げ](https://kiwi-garakuta.pages.dev/tools/kiwi-reading-workbench/) | 画像の文字を確認・修正し、そのまま読み上げ音声に保存する | [RapidOCR](https://github.com/RapidAI/RapidOCR) / [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) |
| [きういファイルしらべ](https://kiwi-garakuta.pages.dev/tools/kiwi-filetype/) | 拡張子がないファイルなどの種類を調べ、候補拡張子・MIMEを一覧保存する | [Magika](https://github.com/google/magika) |
| [きうい画像・PNG工房](https://kiwi-garakuta.pages.dev/tools/kiwi-image-workbench/) | 写真を変換・リサイズし、PNG圧縮と次の編集へ続けて進む | [ImageMagick](https://github.com/ImageMagick/ImageMagick) / [oxipng](https://github.com/oxipng/oxipng) |
| [きういラベル印刷](https://kiwi-garakuta.pages.dev/tools/kiwi-labels/) | 名札・収納ラベルをA4に並べ、文字・余白・枚数を選んでPDFや画像に保存する | [Typst](https://github.com/typst/typst) |
| [きうい動画・GIF工房](https://kiwi-garakuta.pages.dev/tools/kiwi-media-workbench/) | 動画を変換し、短い区間をGIF編集へ渡して順序・速さ・品質を調整する | [FFmpeg](https://github.com/FFmpeg/FFmpeg) / [gifski](https://github.com/ImageOptim/gifski) |
| [きういファイル保存](https://kiwi-garakuta.pages.dev/tools/kiwi-download/) | URLから資料・画像・ZIPなどをまとめて保存し、SHA-256を照合する | [curl](https://github.com/curl/curl) |
| [きういフォルダーコピー](https://kiwi-garakuta.pages.dev/tools/kiwi-copy/) | フォルダーを比較し、不足分だけ内容照合して追加する | [rclone](https://github.com/rclone/rclone) |
| [きうい文書作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-document-workbench/) | Webページを画像ごと保存し、手元の文書と同じ画面でWord・EPUBなどへ変換する | [Pandoc](https://github.com/jgm/pandoc) / [Monolith](https://github.com/Y2Z/monolith) |
| [きういCSV整理](https://kiwi-garakuta.pages.dev/tools/kiwi-table/) | CSVの列選択・絞り込み・並べ替え・重複除去を行う | [DuckDB](https://github.com/duckdb/duckdb) |
| [きういPDF作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-pdf-workbench/) | PDFを編集し、文字・ロゴを重ねて表示・画像保存へ渡す | [qpdf](https://github.com/qpdf/qpdf) / [MuPDF](https://github.com/ArtifexSoftware/mupdf) / [pdfcpu](https://github.com/pdfcpu/pdfcpu) |
| [きうい動画保存](https://kiwi-garakuta.pages.dev/tools/kiwi-video-save/) | 保存が許可された公開動画・音声をURLから1件ずつ保存する | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| [きうい名前整理](https://kiwi-garakuta.pages.dev/tools/kiwi-rename/) | ファイル名の置換・連番を確認して実行し、元に戻す | [F2](https://github.com/ayoisaiah/f2) |
| [きういベクター工房](https://kiwi-garakuta.pages.dev/tools/kiwi-vector/) | ロゴ・イラストをSVGに変換し、色・輪郭を調整して保存する | [VTracer](https://github.com/visioncortex/vtracer) |
| [きうい写真情報](https://kiwi-garakuta.pages.dev/tools/kiwi-photo-info/) | 写真の位置情報・撮影情報を確認し、削除・編集したコピーを作る | [ExifTool](https://github.com/exiftool/exiftool) |
| [きうい圧縮箱](https://kiwi-garakuta.pages.dev/tools/kiwi-archive/) | 写真・書類の圧縮、ZIP・7zなどの中身の確認と新しいフォルダーへの展開 | [ouch](https://github.com/ouch-org/ouch) |
| [きういファイル金庫](https://kiwi-garakuta.pages.dev/tools/kiwi-vault/) | 写真や書類をパスワード・公開鍵で暗号化し、元ファイルを残して復号する | [age](https://github.com/FiloSottile/age) |
| [きういQR](https://kiwi-garakuta.pages.dev/tools/kiwi-qr/) | URL・Wi-FiなどのQRを作り、画像のQR・バーコードを読み取る | [python-qrcode](https://github.com/lincolnloop/python-qrcode) / [ZXing-C++](https://github.com/zxing-cpp/zxing-cpp) |
| [きういバックアップ](https://kiwi-garakuta.pages.dev/tools/kiwi-backup/) | 写真や書類を暗号化して履歴ごとに保存し、別の場所へ復元する | [restic](https://github.com/restic/restic) |
| [きうい重複チェック](https://kiwi-garakuta.pages.dev/tools/kiwi-tidy/) | 同じファイルや似た写真をグループごとに比較し、レポートへ保存する | [Czkawka](https://github.com/qarmin/czkawka) |
| [きうい文字起こし](https://kiwi-garakuta.pages.dev/tools/kiwi-transcribe/) | 録音をPC内で文章・字幕に変換し、英語への翻訳やTXTの修正も行う | [whisper.cpp](https://github.com/ggml-org/whisper.cpp) |
| [きういファイル便](https://kiwi-garakuta.pages.dev/tools/kiwi-transfer/) | 同じWi-Fi・LAN内のPCへ、写真・書類・フォルダーを共有コードで送る | [croc](https://github.com/schollz/croc) |
| [きうい画像拡大](https://kiwi-garakuta.pages.dev/tools/kiwi-image-enlarge/) | 小さな写真・イラストを拡大して仕上がりを見比べる | [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) |
| [きういYAML作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-yaml-workbench/) | YAMLの変換・編集・整形とGitHub Actionsの検査を行う | [yq](https://github.com/mikefarah/yq)・[yamlfmt](https://github.com/google/yamlfmt)・[actionlint](https://github.com/rhysd/actionlint) |
| [きういPC作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-pc-workbench/) | PC構成・空き容量・フォルダー内訳を確認し、共通の対象から重複ファイルを探す | [fastfetch](https://github.com/fastfetch-cli/fastfetch) / [duf](https://github.com/muesli/duf) / [dust](https://github.com/bootandy/dust) / [fclones](https://github.com/pkolaczk/fclones) |
| [きういテキスト作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-text-workbench/) | 例から作った正規表現でテキストやファイルを置換する | [grex](https://github.com/pemistahl/grex)・[sd](https://github.com/chmln/sd) |
| [きういYouTube字幕](https://kiwi-garakuta.pages.dev/tools/kiwi-youtube-captions/) | 字幕の閲覧・検索・翻訳とTXT/SRTなどへの保存 | [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) |
| [きうい検索作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-search-workbench/) | 名前で絞ったファイルから内容を検索する | [fd](https://github.com/sharkdp/fd)・[ripgrep](https://github.com/BurntSushi/ripgrep) |
| [きういJSON作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-json-workbench/) | JSONのツリー閲覧・式変換・パス一覧と復元を同じ入力で行う | [fx](https://github.com/antonmedv/fx)・[gojq](https://github.com/itchyny/gojq)・[jq](https://github.com/jqlang/jq)・[gron](https://github.com/tomnomnom/gron) |
| [きういコード・文書作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-code-workbench/) | コード閲覧・シェル整形・資料生成・Markdown表示を続けて使う | [bat](https://github.com/sharkdp/bat) / [shfmt](https://github.com/mvdan/sh) / [code2prompt](https://github.com/mufeedvh/code2prompt) / [Glow](https://github.com/charmbracelet/glow) |
| [きうい秘密チェック](https://kiwi-garakuta.pages.dev/tools/kiwi-secrets/) | 公開前のフォルダーからAPIキーなどの機密情報候補を探す | [Gitleaks](https://github.com/gitleaks/gitleaks) |
| [きういHTTPビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-http/) | HTTPの応答ヘッダー・本文を確認する | [xh](https://github.com/ducaale/xh) |
| [きういハッシュ](https://kiwi-garakuta.pages.dev/tools/kiwi-hash/) | BLAKE3ハッシュを計算・照合する | [b3sum / BLAKE3](https://github.com/BLAKE3-team/BLAKE3) |
| [きうい色変換](https://kiwi-garakuta.pages.dev/tools/kiwi-color/) | HEX・RGB・HSLを変換して色見本を確認する | [pastel](https://github.com/sharkdp/pastel) |
| [きうい文字絵](https://kiwi-garakuta.pages.dev/tools/kiwi-ascii/) | 静止画像をASCII・点字文字の文字絵に変換する | [ascii-image-converter](https://github.com/TheZoraiz/ascii-image-converter) |
| [きうい比較](https://kiwi-garakuta.pages.dev/tools/kiwi-diff/) | テキスト・コードの差分を表示・保存する | [difftastic](https://github.com/Wilfred/difftastic) |
| [きういコード集計](https://kiwi-garakuta.pages.dev/tools/kiwi-count/) | コードの行数・複雑度・Git履歴を集計し、HTMLレポートを保存する | [scc](https://github.com/boyter/scc) |
| [きういWeb圧縮](https://kiwi-garakuta.pages.dev/tools/kiwi-minify/) | Webファイルの圧縮・連結・フォルダー処理を行う | [minify](https://github.com/tdewolff/minify) |
| [きういデータ変換](https://kiwi-garakuta.pages.dev/tools/kiwi-data/) | 8形式のデータ変換、式による抽出・並べ替え・集計を行う | [dasel](https://github.com/TomWright/dasel) |
| [きういバイト表示](https://kiwi-garakuta.pages.dev/tools/kiwi-bytes/) | バイナリを16進数・文字表で表示し、テキストやC配列に保存する | [hexyl](https://github.com/sharkdp/hexyl) |
| [きうい単位計算](https://kiwi-garakuta.pages.dev/tools/kiwi-calc/) | 単位変換と単位付きの科学計算、プログラム・スクリプト実行 | [Numbat](https://github.com/sharkdp/numbat) |

各ソフトの詳細ページに、使い方、実際の画面、制限事項、ZIPのダウンロード先を掲載しています。ZIPには元ツールのライセンス文書を同梱しています。

## 使い方

1. 上の一覧からソフトの詳細ページを開き、ZIPをダウンロードします。
2. ZIPを任意のフォルダーへ展開します。
3. 中の `KiwiSearchWorkbench.exe`、`KiwiDisk.exe` など、選んだソフトの実行ファイルを起動します。ファイル名と機能は各ソフトの詳細ページとZIP内のREADMEに記載しています。

各ソフトはWindows 11 x64で動作確認しています。現時点の実行ファイルにはコード署名がありません。配布元とZIPの内容を確認してから使用してください。

### 追加オプションを使う

「詳細機能」に対応するソフトでは、メニューから元ツールの追加オプションを指定できます。画像拡大の設定はメイン画面にあります。対応する機能や通常画面との違い、制限は [各ソフトの機能と制限](docs/upstream-feature-audit.md) を参照してください。

## ソースコードとライセンス

GUIのソースコードは [`apps/`](apps/) にあります。このリポジトリのコードは [MITライセンス](LICENSE) で公開しています。元ツールにはそれぞれのライセンスが適用されます。各ソフトの詳細ページと配布ZIP内のライセンス文書を参照してください。

これらのGUIは元ツールの開発者による公式製品ではありません。

## 問い合わせ

不具合や質問は [@kiwi_dori のDM](https://x.com/kiwi_dori) へお寄せください。お問い合わせの際は、ソフト名・バージョンと、問題が起きた操作やエラーメッセージをお知らせください。画像やログを添える場合は、個人情報を取り除いてください。

## 開発を支援する

ソフトは無料で利用できます。役に立った場合は、各ソフトの詳細ページにあるPayPalリンクから開発を支援できます。
