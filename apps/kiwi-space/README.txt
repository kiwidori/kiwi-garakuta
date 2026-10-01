きうい空き容量 0.1.0
Windows 11 x64向け・インストーラーなしの無料ZIP版

dufの非公式GUIです。元ツールの開発者とは関係ありません。
1. ZIPを展開し、KiwiSpace.exeを起動します。
2. 「更新」を押し、ドライブの容量を取得します。
3. 列見出しをクリックして並べ替えます。
4. 行を選んでコピーするか、一覧をCSVとして保存できます。

対象はdufがローカルと分類した、ドライブ文字付きのWindowsドライブです。
仮想ドライブが含まれる場合があります。フォルダーにマウントされたボリュームは表示しません。
ネットワークと分類されたドライブは対象外です。ドライブの応答状態によって取得できない場合があります。
取得時点の情報を表示します。自動更新・履歴保存・通知機能はありません。
容量はGiB/TiB（1024基準）で表示し、CSVの容量はバイト単位です。
使用率は使用量÷総容量です。Windowsやドライバーの集計方法によって見え方が異なる場合があります。
取得は15秒、エンジン出力は1MiBまでです。
ファイルの走査・削除・クリーンアップは行いません。ドライブ名や個人のPCパスは表示・CSVに含めません。
CSVはUTF-8 BOM付きです。CSVの保存先だけに書き込みます。
現時点の実行ファイルにはコード署名がありません。

上流: https://github.com/muesli/duf （v0.9.1、MIT）
duf-LICENSE、duf-README.md、THIRD-PARTY-NOTICES.txt、Runtime-LICENSES.txtを同梱しています。
GUIのライセンス: LICENSE （MIT）
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-space
問い合わせ: https://x.com/kiwi_dori
