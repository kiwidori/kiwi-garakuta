きうい正規表現 0.1.0

Windows 11 x64向けの無料ツールです。ZIPを展開してKiwiRegex.exeを起動します。
一致させたい文字列を1行ずつ入力し、「生成」を押すとgrexで正規表現を作ります。
空の行は無視します。空白だけの行や、行の前後の空白は入力の一部です。
結果は「コピー」でクリップボードへコピーできます。外部への送信は行いません。

「数字を一般化」は数字を\dへ変え、例にない数字にも一致するようになります。
「大小文字を区別しない」は大小文字を同じものとして扱います。
「繰り返しをまとめる」は繰り返しを量指定子で表します。
オプションによって一致範囲が広がります。生成結果は実際に使う正規表現エンジンで確認してください。
正規表現を実行して判定する機能はありません。例から意図や業務上のルールを推測するものではありません。

入力はUTF-8で16 KiBまで、100行まで、1行256文字までです。生成結果は64 KiB、処理時間は15秒までです。
元ツールgrex: https://github.com/pemistahl/grex
このソフトはgrex開発者の公式製品ではありません。
Copyright 2019-present Peter M. Stahl. grexのApache License 2.0はgrex-LICENSEを参照してください。
GUIのライセンスはLICENSEを参照してください。
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-regex
問い合わせ: https://x.com/kiwi_dori
現時点の実行ファイルにはコード署名がありません。環境によってはMicrosoft Visual C++ Redistributableが必要です。
