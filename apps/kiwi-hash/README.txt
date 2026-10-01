きういハッシュ 0.1.0

Windows 11 x64向けの無料ツールです。ZIPを展開してKiwiHash.exeを起動します。
ファイルを選んで「計算」を押すと、b3sumでBLAKE3ハッシュを計算します。
照合値に64文字のBLAKE3ハッシュを入力すると、一致・不一致を確認できます。
計算したハッシュは「コピー」でクリップボードにコピーできます。
ファイルは変更せず、外部への送信も行いません。

BLAKE3専用です。SHA-256など他の方式の値とは比較できません。
ハッシュ一致は配布元やファイルの安全性を保証しません。照合値の入手元も確認してください。
入力は8 GiB、処理は120秒までです。計算中にファイルのサイズや更新日時などが変わると結果を破棄します。
ファイル更新を完全に検知する仕組みではありません。更新中のファイルは対象にしないでください。

元ツールb3sum/BLAKE3: https://github.com/BLAKE3-team/BLAKE3
このソフトはBLAKE3開発者の公式製品ではありません。上流のライセンス文書はb3sum-LICENSE_A2、b3sum-LICENSE_A2LLVM、b3sum-LICENSE_CC0、GUIのMITライセンスはLICENSEを参照してください。
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-hash
問い合わせ: https://x.com/kiwi_dori
現時点の実行ファイルにはコード署名がありません。
