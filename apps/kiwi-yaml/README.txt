きういYAML 0.1.0

Windows 11 x64向けの無料ツールです。ZIPを展開してKiwiYAML.exeを起動します。
UTF-8の.yaml/.ymlファイルを選び、「YAML整形」または「JSON変換」を選んで実行します。
yqで処理した結果を画面で確認し、「保存」で新しいファイルに保存できます。
元ファイルや既存ファイルは上書きしません。ファイルを外部へ送信しません。

入力は2 MiB、結果は4 MiB、処理は15秒までです。画面の表示は先頭120,000文字までで、保存は結果全体です。
JSON変換ではコメント・アンカー・タグなどの表現が変わったり失われたりします。
複数のYAML文書は複数のJSON値として出力され、単一の配列にはなりません。
整形・変換後は利用先で内容を確認してください。変換前の表現への復元は保証しません。

元ツールyq: https://github.com/mikefarah/yq
このソフトはyq開発者の公式製品ではありません。yqのMITライセンスはyq-LICENSE、GUIのライセンスはLICENSEを参照してください。
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-yaml
問い合わせ: https://x.com/kiwi_dori
現時点の実行ファイルにはコード署名がありません。
