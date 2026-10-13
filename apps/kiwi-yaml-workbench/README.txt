きういYAML作業場 0.1.0 — Windows 11 x64

ZIPを展開してKiwiYamlWorkbench.exeを起動します。
用途から「変換・編集」「整形・差分」「Actions検査」を選びます。
テキストを入力するか、ファイル・フォルダーを指定します。両方を同時に指定しないでください。
変換・整形した本文を「結果を入力へ」で次の処理へ渡せます。ファイル指定は解除されます。
結果は保存するまで元ファイルへ反映しません。ZIPや検査レポートは入力へ移せません。
各用途の設定は起動中に保持されます。詳細画面の設定は用途を切り替えると初期状態になります。

変換・編集: YAML整形、JSON変換、yq式での抽出・更新・複数文書処理。
整形・差分: Basic/KYAML、整形設定、差分・整形チェック、設定の読み込みと保存、一括整形ZIP。
Actions検査: GitHub Actions専用の検査、JSON・独自形式のレポート、設定生成。
Actionsの検査は一般的なYAMLの検査ではありません。ワークフローは実行しません。

テキストと入力への移送はUTF-8で2 MiBまで。NULを含む結果は移送できません。
yqは1ファイル2 MiB・200件・合計64 MiB、式16 KiB、出力4 MiB・15秒まで。
yamlfmtは2,000ファイル・合計64 MiB、actionlintは200ファイル・1件20 MiB・合計64 MiB。
整形・検査は出力16 MiB・300秒まで。通常のファイル指定にリンクやジャンクションは使えません。
JSON変換ではコメント・タグなどが失われる場合があります。複数文書は複数のJSON値になります。
yqの環境変数・外部ファイル読み込み・system式・直接上書きを無効にしています。
外部ShellCheck/Pyflakesは指定した場合だけ呼び出します。詳細オプションの出力は各ツールの仕様に従います。
コード署名はありません。

非公式GUI。yq 4.54.1 (MIT): https://github.com/mikefarah/yq
yamlfmt 0.21.0 (Apache-2.0): https://github.com/google/yamlfmt
actionlint 1.7.12 (MIT): https://github.com/rhysd/actionlint
ライセンス・依存物・実行環境の文書を同梱しています。
配布ページ: https://kiwi-garakuta.pages.dev/tools/kiwi-yaml-workbench/
問い合わせ: https://x.com/kiwi_dori
