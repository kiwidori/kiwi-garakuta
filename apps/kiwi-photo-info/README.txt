きうい写真情報 0.1.0

写真の撮影日時、カメラ、位置情報などを確認し、共有前に整理するWindows 11 x64用ソフトです。

使い方
1. ZIPを通常の書き込み可能なフォルダーへすべて展開し、KiwiPhotoInfo.exeを起動します。
2. 初回のみ「ExifToolを準備」を押します。公式配布元のSourceForgeからExifTool 13.59のWindows 64bit版（約11 MB）を取得します。SHA-256を照合し、元のライセンス文書を含めてnative/に展開します。以後はオフラインで使えます。
3. ファイルを選び「情報を読む」で一覧を表示します。タグ・値を検索し、選択値のコピーやJSON・CSV保存ができます。
4. 「コピーを作って整理する」で操作を選び、保存先を指定します。結果は新しい「写真情報-日時-識別子」フォルダーへ保存し、保存したファイルの情報を表示します。

整理できる内容
・EXIF GPS、XMPのGPS・場所、IPTCの地域情報を削除
・ExifToolで削除可能なメタデータをまとめて削除（向き・ICCプロファイルを残す設定あり）
・撮影者、著作権、タイトル、説明、撮影日時の変更・削除
・EXIF/IPTC/XMPの追加タグ（グループ:タグ=値、1行1項目）
・EXIF AllDatesの時刻を±168時間まで補正（整数時間）
・別の写真やXMPから書き込み可能なタグをコピー
・XMPサイドカーを書き出し

制限
保存処理はJPEG・PNG・WebPのみです。他の形式はExifToolが読み取れる情報の確認だけに使えます。形式やタグによって書き込めない項目があります。警告と保存結果を確認してください。
元ファイルは削除・上書きしません。100ファイル、各256 MiB、合計1 GiB、一括処理5分までです。読み取り結果は合計16 MiB、画面一覧は最大12,000行です。JSON・CSVは読み込めた全項目を保存します。
場所を示す独自タグや文章が残る場合があります。写真の中に写った住所・人物・文字は消えません。完全な匿名化を保証しません。
向き・ICCプロファイルを残す設定では、それらの情報は残ります。オフにすると色や表示方向が変わる場合があります。
情報のレポートには位置情報・フルパスなどが含まれます。公開・共有する前に内容を確認してください。
RAW・HEIC・動画・PDFへの書き込み、任意のCLI引数、ユーザー設定スクリプト、ファイル名変更、GPS軌跡の埋め込み、常駐サーバー、ExifToolの全オプション互換には対応しません。
初回の通信はツールの取得だけです。写真はサーバーへ送信しません。

元ソフト・ライセンス
ExifTool by Phil Harvey: https://exiftool.org/ / https://github.com/exiftool/exiftool
ExifToolはPerlと同じ条件（Perl Artistic LicenseまたはGPL）で配布されています。このZIPはExifTool・Perlの実行ファイルを同梱しません。初回に取得する公式パッケージのLICENSE、readme_windows.txt、Licenses_Strawberry_Perl.zipなどを参照してください。上流の非公式GUIです。
GUIコード：MIT（LICENSE）。Python/Tcl/Tk/PyInstallerの通知はRuntime-LICENSES.txtとPyInstaller-LICENSE.txtを参照してください。

配布・問い合わせ
https://kiwi-garakuta.pages.dev/tools/kiwi-photo-info/
https://github.com/kiwidori/kiwi-garakuta
https://x.com/kiwi_dori
