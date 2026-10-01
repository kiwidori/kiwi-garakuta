きういJSON 0.1.0

Windows 11 x64向けの無料ツールです。KiwiJSON.exeを起動し、JSONファイルとjq抽出式を指定してください。
「実行」で結果を表示し、「結果を保存」で出力を別ファイルに書き出せます。元のJSONファイルは変更しません。

抽出式の例:
  .                         JSON全体を整形
  .items[]                   items配列の各要素を表示
  .items[] | {name, price}   各要素から名前と価格を取り出す

入力は20 MiBまで、結果は2 MiBまで、処理時間は20秒までです。プレビューは先頭120,000文字まで表示しますが、保存時は結果全体を書き出します。抽出式によっては複数のJSON値が出力されるため、保存時の既定拡張子は.txtです。単一のJSON値にした場合は.jsonを選べます。

元ツール jq: https://github.com/jqlang/jq
このソフトはjq開発者の公式製品ではありません。jqのライセンスと同梱コードの第三者通知はjq-COPYINGを参照してください。GUIのライセンスはLICENSEを参照してください。
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-json
問い合わせ: https://x.com/kiwi_dori

この実行ファイルにはコード署名がありません。
