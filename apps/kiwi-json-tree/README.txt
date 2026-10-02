きういJSONツリー 0.1.0
Windows 11 x64 / ZIPを展開し、KiwiJsonTree.exeを起動してください。

JSON・YAML・TOMLをツリーで読み、選んだ値やパスをコピーできます。
生テキストは行ごとの文字列として読めます。
「ツリー用JSONを読み込む」→「結果をツリーで開く」で閲覧します。
「式を実行」ではJavaScriptの式を1行1段で入力します。
例: .items / map(x=>x.price) / sort / len
文字列の出力など、JSONとして読めない結果はテキストで確認してください。

ツリーの項目削除は表示中のデータだけを変更します。元の入力ファイルは変わりません。
「元に戻す」で読み込み直後へ戻せます。選択値の保存は別のファイル名を指定してください。
大きな整数と小数は読み込み時の表記を保持します。JavaScriptで浮動小数点の演算を行うと精度が変わることがあります。

入力UTF-8、2 MiBまで。1ファイル、またはテキストを指定します。
出力16 MiB、1回300秒、式32段まで。ツリーは最大2万項目・深さ80までです。
ツリー内検索は文字検索です。重複キーは最後の値を表示します。
端末用テーマ・補完・ゲーム、外部エディター、既存.fxrc.jsの自動読み込みは使いません。
JavaScriptはfx内蔵エンジンで実行し、Node.jsやブラウザーのAPIは使えません。

紹介・使い方: https://kiwi-garakuta.pages.dev/tools/kiwi-json-tree/
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-json-tree
元ツール: fx 39.2.0 / https://github.com/antonmedv/fx
非公式GUIです。ライセンス文書と依存物通知をZIPへ同梱しています。
問い合わせ: https://x.com/kiwi_dori
