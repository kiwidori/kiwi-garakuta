# 機能と制限

各ソフトの使い方、設定できる項目、制限は、以下のリンク先に掲載しています。

| ソフト | 主な用途 |
| --- | --- |
| [きうい検索作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-search-workbench/) | 名前検索の結果を内容検索へ渡し、共通の対象と除外で検索 |
| [きうい検索](https://kiwi-garakuta.pages.dev/tools/kiwi-search/) | フォルダー内の文章を検索し、該当する行を表示 |
| [きういファイル探し](https://kiwi-garakuta.pages.dev/tools/kiwi-find/) | 名前や拡張子からファイルを探す |
| [きうい容量ビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-disk/) | 容量の大きいファイルやフォルダーを確認する |
| [きういJSON](https://kiwi-garakuta.pages.dev/tools/kiwi-json/) | JSONから必要なデータを取り出し、結果を保存する |
| [きういJSON作業場](https://kiwi-garakuta.pages.dev/tools/kiwi-json-workbench/) | JSONツリー・式・パス一覧と復元を共通の入力と結果で利用 |
| [きういコードビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-code/) | コードやテキストを色付き・行番号付きで閲覧する |
| [きういPC情報](https://kiwi-garakuta.pages.dev/tools/kiwi-system/) | OS・CPU・GPU・メモリなどPCの概要を確認する |
| [きうい秘密チェック](https://kiwi-garakuta.pages.dev/tools/kiwi-secrets/) | 公開前のフォルダーからAPIキーなどの機密情報候補を探す |
| [きうい正規表現](https://kiwi-garakuta.pages.dev/tools/kiwi-regex/) | 文字列の例から正規表現を作る |
| [きういHTTPビュー](https://kiwi-garakuta.pages.dev/tools/kiwi-http/) | HTTPの応答ヘッダー・本文を確認する |
| [きういPNG圧縮](https://kiwi-garakuta.pages.dev/tools/kiwi-png/) | PNGを圧縮して別ファイルへ保存する |
| [きういYAML](https://kiwi-garakuta.pages.dev/tools/kiwi-yaml/) | YAMLを整形し、JSONへ変換する |
| [きういハッシュ](https://kiwi-garakuta.pages.dev/tools/kiwi-hash/) | BLAKE3ハッシュを計算・照合する |
| [きうい色変換](https://kiwi-garakuta.pages.dev/tools/kiwi-color/) | HEX・RGB・HSLを変換して色見本を確認する |
| [きうい文字絵](https://kiwi-garakuta.pages.dev/tools/kiwi-ascii/) | 静止画像をASCII・点字文字の文字絵に変換する |
| [きうい空き容量](https://kiwi-garakuta.pages.dev/tools/kiwi-space/) | ドライブの容量を一覧表示・CSV保存する |
| [きうい比較](https://kiwi-garakuta.pages.dev/tools/kiwi-diff/) | テキスト・コードの差分を表示・保存する |
| [きういコード集計](https://kiwi-garakuta.pages.dev/tools/kiwi-count/) | コードの行数・複雑度・Git履歴を集計し、HTMLレポートを保存する |
| [きういシェル整形](https://kiwi-garakuta.pages.dev/tools/kiwi-shell/) | シェルの整形・差分・AST変換と一括整形を行う |
| [きういWeb圧縮](https://kiwi-garakuta.pages.dev/tools/kiwi-minify/) | Webファイルの圧縮・連結・フォルダー処理を行う |
| [きういデータ変換](https://kiwi-garakuta.pages.dev/tools/kiwi-data/) | 8形式のデータ変換、式による抽出・並べ替え・集計を行う |
| [きういMarkdown](https://kiwi-garakuta.pages.dev/tools/kiwi-markdown/) | Markdown・URL・READMEを装飾付きで表示し、テキストを保存する |
| [きうい置換](https://kiwi-garakuta.pages.dev/tools/kiwi-replace/) | 文字列・正規表現でテキストと複数ファイルを置換して保存する |
| [きういバイト表示](https://kiwi-garakuta.pages.dev/tools/kiwi-bytes/) | バイナリを16進数・文字表で表示し、テキストやC配列に保存する |
| [きうい単位計算](https://kiwi-garakuta.pages.dev/tools/kiwi-calc/) | 単位変換と単位付きの科学計算、プログラム・スクリプト実行 |
| [きういコード資料](https://kiwi-garakuta.pages.dev/tools/kiwi-prompt/) | コード・Git情報をLLM向け資料にまとめ、トークン分布を確認する |
| [きういYAML整形](https://kiwi-garakuta.pages.dev/tools/kiwi-yamlfmt/) | YAMLの整形・差分・整形チェックと一括ZIP保存 |
| [きういJSONパス](https://kiwi-garakuta.pages.dev/tools/kiwi-json-paths/) | JSONのパス一覧化・復元・トークン抽出 |
| [きういActions点検](https://kiwi-garakuta.pages.dev/tools/kiwi-actions-check/) | GitHub Actionsの点検・JSONレポート・設定YAML |
| [きういJSON式](https://kiwi-garakuta.pages.dev/tools/kiwi-json-expr/) | JSON・YAMLの式処理・変数・大きな整数計算 |
| [きういJSONツリー](https://kiwi-garakuta.pages.dev/tools/kiwi-json-tree/) | JSON・YAML・TOMLのツリー閲覧とJavaScript式の処理 |

## 詳細機能の使い方

メニューの「詳細機能」から、元ツールの追加オプションを指定できます。オプションを選び、必要な値やファイルを入力して実行します。使える引数は画面内のヘルプで確認できます。

元ツールのすべての操作が使えるわけではありません。シェルのパイプやリダイレクト、端末での対話操作には対応していません。

## 詳細機能の制限

- 実行時間は1回300秒、標準入力は2 MiB、出力は標準出力とエラーを合わせて16 MiB、引数は256個までです。
- ripgrepの外部前処理、fdのコマンド実行、batの外部ページャー、pastelの外部色ピッカー、fastfetchの外部設定ファイルは使えません。
- きういYAMLでは、環境変数・外部ファイルの読み込み、system式、入力ファイルへの直接上書きを無効にしています。変更した結果は別ファイルへ保存できます。
- きうい秘密チェックでは検出した秘密の値をマスクします。詳細画面での設定ファイル・テンプレート・診断サーバー・任意のgit log引数は使えません。Git履歴の検査にはGitのインストールが必要です。
- きういHTTPビューではセッションの保存に対応していません。認証情報を自動保存しません。
- Windows版の元ツールが対応していない機能は使えません。

ファイルへの書き込みや通信を行うオプションもあります。実行前に入力・出力の場所や送信先を確認してください。

各ソフト固有の入力サイズや一括処理の上限は、個別ページとZIP内のREADMEに記載しています。設定の組み合わせによっては元ツールがエラーを返すことがあります。
