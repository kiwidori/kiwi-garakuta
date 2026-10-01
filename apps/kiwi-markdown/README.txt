きういMarkdown 0.1.0 / Windows 11 x64

ZIPを展開してKiwiMarkdown.exeを起動してください。インストールは不要です。
Glow v3.0.0を使う非公式GUIです。元ツールの開発者による製品ではありません。

使い方
1. 操作を選び、Markdownを入力するか1ファイルを指定します。
   「デモ」で表示例を試せます。ファイルは自動で変更しません。
2. 表示設定でスタイル、折り返し幅、改行保持を指定します。
   light/dark/ascii/tokyo-night/nottyのボタン、独自JSONスタイルも利用できます。
3. 実行すると見出し、表、太字、斜体、打ち消し線、コードなどを整えて表示します。
4. 「プレーン保存」で装飾のないテキストを保存できます。
   「ANSIテキストを保存」は元の色・装飾コードを含む出力を保存します。

URL操作ではHTTP(S)の文書、github://所有者/リポジトリ、
gitlab://所有者/リポジトリなどを指定できます。取得はGlowが行います。
メニュー「詳細機能」では追加引数、標準入力、ヘルプ、補完・マニュアルの出力を扱えます。
補完スクリプトを自動実行する機能はありません。

制限
標準入力と通常画面のファイルは2 MiBまで。通常画面は1ファイルずつです。
1回300秒、標準出力・標準エラー合計16 MiB、引数256個/64 KiB。
画面の装飾表示は先頭128 KiBまでです。保存は取得できた全出力を使います。
URLや詳細機能からのファイルの読込容量はGlow側に従います。
端末UI、外部ページャー、外部エディタ、端末用の隠し項目・行番号・マウス設定は対象外。
個人のGlow設定・環境変数は引き継がず、画面で指定した表示設定を使います。
ANSI装飾はGUIで表現できる範囲で表示します。HTMLやJavaScriptは実行しません。
全文書・全スタイル・全オプションの組合せを検証した製品ではありません。実行ファイルは未署名です。

ライセンスとソース
GUI: MIT https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-markdown
Glow: MIT https://github.com/charmbracelet/glow/tree/v3.0.0
UPSTREAM-LICENSE.txt / THIRD-PARTY-NOTICES.txt / Runtime-LICENSES.txtを参照してください。
変更していない依存物の版、ライセンス全文、ソースの取得先も同梱しています。

問い合わせ: https://x.com/kiwi_dori
配布サイト: https://kiwi-garakuta.pages.dev/tools/kiwi-markdown/
