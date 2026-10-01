きういデータ変換 0.1.0 / Windows 11 x64

ZIPを展開してKiwiData.exeを起動してください。インストールは不要です。
dasel v3.11.2 の非公式GUIです。元ツールの開発者による製品ではありません。

使い方
1. UTF-8ファイルを読み込むか、入力欄へデータを貼り付けます。
2. 入出力タブで形式を選びます。JSON/YAML/TOML/XML/CSV/HCL/INI/KDLに対応。
   入力のみdasel式も選べます。JSON指定でNDJSONも読み込めます。
3. クエリ欄へ式を指定します。空欄または$thisは形式変換のみです。
4. 実行して結果を確認し、「結果を保存」で別ファイルへ保存します。
   読み込んだファイルは自動で変更しません。

式の例はデモデータ用です。サンプルを読み込んでからお試しください。
詳細設定で変数、読込・出力設定、実験的機能、設定ファイルを指定できます。
設定ファイルは初期値NULで、ホームの個人設定を読み込みません。
メニュー「詳細機能」には追加引数、標準入力、ヘルプ、補完・マニュアルの例があります。
補完スクリプトの自動実行、端末用対話モードは提供しません。

制限
UTF-8入力2 MiB、引数256個/64 KiB、標準出力・標準エラー合計16 MiB、1回300秒。
CSV・XML等へ変換できる構造はdaselの各形式の制限に従います。
dasel v3.11.2の式に日本語文字列を直接書くと解析に失敗する場合があります。
日本語の値は入力データまたは変数例 changed=json:"日本語" で渡し、式title=$changedで参照できます。
全ての式・フラグの組合せを検証した製品ではありません。実行ファイルは未署名です。
daselのreadFile()やファイル変数は、指定したローカルファイルを読み込みます。

ライセンスとソース
GUI: MIT https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-data
dasel: MIT https://github.com/TomWright/dasel/tree/v3.11.2
UPSTREAM-LICENSE.txt / THIRD-PARTY-NOTICES.txt / Runtime-LICENSES.txtを参照してください。
依存物の版・ライセンス全文・変更していないソースの取得先も同梱しています。

問い合わせ: https://x.com/kiwi_dori
配布サイト: https://kiwi-garakuta.pages.dev/tools/kiwi-data/
