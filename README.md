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

各ソフトの詳細ページに、使い方、実際の画面、制限事項、ZIPのダウンロード先を掲載しています。ZIPには元ツールのライセンス文書を同梱しています。

## 使い方

1. 上の一覧からソフトの詳細ページを開き、ZIPをダウンロードします。
2. ZIPを任意のフォルダーへ展開します。
3. 中の `KiwiSearch.exe`、`KiwiFind.exe`、`KiwiDisk.exe`、`KiwiJSON.exe`、`KiwiCode.exe`、`KiwiSystem.exe`、`KiwiSecrets.exe`、`KiwiRegex.exe`、または `KiwiHTTP.exe` を起動します。

各ソフトはWindows 11 x64で動作確認しています。現時点の実行ファイルにはコード署名がありません。配布元とZIPの内容を確認してから使用してください。

## ソースコードとライセンス

GUIのソースコードは [`apps/`](apps/) にあります。このリポジトリのコードは [MITライセンス](LICENSE) で公開しています。元ツールにはそれぞれのライセンスが適用されます。各ソフトの詳細ページと配布ZIP内のライセンス文書を参照してください。

これらのGUIは元ツールの開発者による公式製品ではありません。

## 開発について

サイトは `catalog.json` をもとに `python site/build.py` で生成します。ソフトは `apps/` 内の各フォルダーにあり、`verify.py` で主要機能、`smoke_zip.py` で完成ZIPの起動と同梱物を確認できます。配布ビルドは `build.py` を参照してください。

不具合や質問は [@kiwi_dori のDM](https://x.com/kiwi_dori) へお寄せください。開発を支援したい場合は、各ソフトの詳細ページにPayPalリンクがあります。
