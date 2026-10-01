きうい秘密チェック 0.1.0

Windows 11 x64向けの無料ツールです。ZIPを展開してKiwiSecrets.exeを起動します。
フォルダーを選んで「チェック」を押すと、Gitleaksの標準ルールでAPIキーなどの機密情報の候補を探します。
結果にはファイルの相対パス、行番号、検出ルールを表示し、検出した秘密の値や本文は表示しません。
結果をダブルクリックすると、そのファイルのあるフォルダーを開きます。チェック対象のファイルは変更しません。

現在のファイルのみをチェックします。Git履歴、圧縮ファイルの中身、エンコードされた値の復号は対象外です。
5 MBを超えるファイルはスキップします。Gitleaks標準ルールの除外設定が適用されます。表示は最大1000件、結果データは4 MiB、処理は120秒までです。
誤検出や見逃しがあります。「候補なし」は機密情報が存在しないことを保証しません。
外部サービスへの送信や、検出した値の有効性確認は行いません。

元ツール Gitleaks: https://github.com/gitleaks/gitleaks
このソフトはGitleaks開発者の公式製品ではありません。GitleaksのMITライセンスはgitleaks-LICENSE、GUIのライセンスはLICENSEを参照してください。
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-secrets
問い合わせ: https://x.com/kiwi_dori

この実行ファイルにはコード署名がありません。
