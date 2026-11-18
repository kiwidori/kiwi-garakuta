きうい動画一覧シート 0.1.0 — Windows 11 x64

動画から場面を等間隔に抜き出し、時刻付きの一覧画像を作ります。
ゲーム録画や旅行動画の中身を見渡したいときに使えます。

1. ZIPをすべて展開してKiwiVideoSheet.exeを起動します。
2. 初回のみ「エンジンを準備」で、FFmpeg公式サイトから案内されている
   Gyan配布のWindows版（約100 MB）を取得します。
3. 動画、場面の枚数、列数、1コマの幅を選び「一覧を作る」を押します。
4. 「画像を確認」で仕上がりを見てから、PNGかJPEGで別名保存します。

詳細設定で開始・終了の秒数、明るい／暗い背景、動画名・時刻の表示を選べます。
指定範囲を等分した各区間の中央を抽出します。時刻は抽出指定位置のため、
実際のフレーム位置とはわずかに異なる場合があります。縦長の映像は余白を
付けて表示し、切り抜きません。表示名にはファイル名だけを使います。
元動画や同名の出力は上書きしません。準備後の処理はPC内で行います。

入力：MP4/MOV/MKV/WebM/AVI/M4V/MPG/MPEG/TSの単一ローカル動画。
512 MiB・60分以内、各辺4096px・900万画素まで。音声は不要です。
通常の最初の映像トラックを使います。4～36コマ、2～6列、コマ幅160～480px。
出力は各辺4096px・1600万画素・PNG32 MiBまでです。大きすぎる組み合わせは
枚数やコマ幅を減らしてください。JPEGは品質90で保存します。
各コマ30秒、全体10分、エンジンは1プロセス512 MiBまでの処理です。
ネットワークパス・リンク・ジャンクション・URL・ライブ配信は扱いません。
シーンの自動選別、動画の再生・編集、複数動画の一括処理、音声編集、
全FFmpeg機能を操作する画面はありません。

エンジンの元ZIPはこの配布物に含めません。初回に固定版とSHA-256を確認し、
FFmpeg 9.0.2の元のライセンス・文書も展開先へ保存します。
FFmpeg：https://github.com/FFmpeg/FFmpeg
Windows配布元：https://github.com/GyanD/codexffmpeg
公式ダウンロード案内：https://ffmpeg.org/download.html
配布物に含むPython・Tk・Pillow等の通知も同梱しています。

使い方：https://kiwi-garakuta.pages.dev/tools/kiwi-video-sheet/
ソース：https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-video-sheet
問い合わせ：https://x.com/kiwi_dori
