きういJSON作業場 0.1.0 / Windows 11 x64
ZIPを展開してKiwiJsonWorkbench.exeを起動してください。

JSONツリー・JSON式・JSONパスの機能を、同じ入力と結果で使えるソフトです。
1. 用途を選び、データを貼り付けるかファイルを指定します。
2. 入力形式や式を設定して実行します。通常画面の設定は、起動中に用途を切り替えても保持します。
3. 「結果を入力へ」で次の処理へ渡せます。ファイル指定とURL指定は解除されます。
4. JSONの結果はツリーで開き、選択値・キー・パスをコピーできます。
5. 原文を保存する場合は「結果を保存」を使います。色を除いて保存する操作もあります。

ツリー閲覧・JavaScript: fx 39.2.0 / https://github.com/antonmedv/fx
JSON式（jq形式）: gojq v0.12.19 / https://github.com/itchyny/gojq
JSONパスの一覧・復元: gron v0.7.1 / https://github.com/tomnomnom/gron
jqとgojqは完全互換ではありません。形式や式は各用途の設定に従います。

入力欄と結果の入力への移送は2 MiBまでです。NULを含む出力は入力欄へ移せません。
ファイル入力・変数・モジュールの制限は各ツールの仕様に従います。
出力16 MiB、1回300秒。ツリーは最大2万項目・深さ80、重複キーは最後の値を表示します。
元ファイルを自動で変更しません。ツリー内検索は文字検索です。
非JSONの結果はテキストで確認してください。
gojqの整数演算とfxの読み込みは大きな整数を扱えますが、浮動小数点の演算やgronでの変換は元ツールの数値制約に従います。
端末専用のテーマ・補完・ゲーム、外部エディター、.fxrc.jsの自動読み込みは使いません。
各上流ライセンス・依存物・実行環境の通知を同梱しています。

使い方: https://kiwi-garakuta.pages.dev/tools/kiwi-json-workbench/
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-json-workbench
問い合わせ: https://x.com/kiwi_dori
