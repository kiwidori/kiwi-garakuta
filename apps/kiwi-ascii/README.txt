きうい文字絵 0.1.0
Windows 11 x64向け・インストーラーなしの無料ZIP版

ascii-image-converterの非公式GUIです。元ツールの開発者とは関係ありません。
1. ZIPを展開し、KiwiASCII.exeを起動します。
2. ローカルの静止画像を選択します。
3. 横幅（20〜160文字）、白黒反転、点字文字を指定し、変換します。
4. 結果をコピーするか、UTF-8のテキストとして保存します。

PNG・JPEG・BMP・WEBP・TIFFの単一フレーム画像が対象です。
GIF・動画・アニメーション・複数ページ画像・URLの取得には対応しません。
画像は20MiB・2,000万画素以下、文字絵の想定高さ400行以下です。
処理は30秒、出力は1MiBまでです。元画像を変更せず、外部へ送信しません。
透明な部分や色の違いの表現は元エンジンの仕様に依存します。
点字文字は表示先のフォントによって見え方が変わります。等幅フォントで表示してください。
保存先に入力画像と同じファイルは指定できません。上書きは保存ダイアログで確認します。
現時点の実行ファイルにはコード署名がありません。

上流: https://github.com/TheZoraiz/ascii-image-converter （v1.13.1、Apache 2.0）
ascii-image-converter-LICENSE.txt、ascii-image-converter-README.md、
THIRD-PARTY-NOTICES.txt、Pillow-LICENSE.txt、Runtime-LICENSES.txtを同梱しています。
GUIのライセンス: LICENSE （MIT）
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-ascii
問い合わせ: https://x.com/kiwi_dori
