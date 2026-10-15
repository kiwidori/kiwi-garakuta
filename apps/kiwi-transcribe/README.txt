きうい文字起こし 0.1.0 / Windows 11 x64

録音した音声を文章と字幕へ変換します。音声はPC内で処理し、外部へ送信しません。
日本語対応のWhisper small-q5_1モデルと、無音検出用のSileroモデルを同梱しています。
GPUやAPIキーは不要です。

1. ZIPを展開してKiwiTranscribe.exeを起動します。
2. WAV・MP3・FLAC・OGG（Vorbis）を追加し、保存先のフォルダーを選びます。
3. 操作と言語、保存形式を選んで「開始」を押します。
4. 結果は新しい「文字起こし-...」フォルダーへ保存されます。元音声と既存ファイルは変更しません。
5. 文章を確認し、必要なら修正して別名のTXTへ保存してください。

文字起こしのほか、英語への翻訳、言語の判別のみも選べます。
保存形式はTXT・SRT・VTT・LRC・CSV・JSONです。初期状態ではTXT・SRT・VTTを保存します。
言語判別のみの場合はJSONを保存します。詳細のlog-scoreでスコアの報告も保存できます。
表示した文章の修正は、既に保存した字幕・JSONなどには反映されません。

追加設定では開始位置・長さ、固有名詞などの指定、無音を除くVAD、ステレオの左右区別、互換GGMLモデルを指定できます。
長さ0は音声の終わりまでです。VADとCPU分割（processors）では、開始位置と長さを0にしてください。
開始位置・対象時間と字幕の時刻は目安です。認識の区切りによって指定範囲の前後が含まれる場合があります。
音声ファイル自体を切り取る機能ではありません。
左右の区別はステレオ録音用で、同じチャンネルの中で人ごとの話者を識別するものではありません。
VADは初期状態でオフです。使うと無音を除けますが、発話の一部が欠けることもあります。

Windows 11 x64とMicrosoft Visual C++ v14再頒布可能パッケージ（x64）が必要です。
https://learn.microsoft.com/ja-jp/cpp/windows/latest-supported-vc-redist
初回起動と処理中に作業用の空き容量を使います。1 GB以上の空き容量を推奨します。
1件200 MiB・最長1時間、20件・合計1 GiBまで。事前確認は90秒、認識処理は1件30分、保存ファイルは各16 MiBまでです。
失敗・停止した回は新しい結果を保存しません。過去の保存結果はそのまま残ります。
音声の状態や言語・モデルによって、誤認識や音声にない文章が生じる場合があります。結果を確認してください。
CSVの文章が数式として解釈されそうな場合は先頭にアポストロフィを付けます。
M4A・MP4・動画・マイク録音、GPU/OpenVINO、Unix用カラオケスクリプトには対応していません。
互換Whisper GGMLモデルは手元から選べます。GGUFは使えません。tinydiarizeには別途専用TDRZモデルが必要です。
コード署名はありません。

whisper.cpp 1.9.5（公式ビルドb5454）の非公式GUIです。
元ツール: https://github.com/ggml-org/whisper.cpp
モデル: https://huggingface.co/ggerganov/whisper.cpp
ソース: https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-transcribe
配布・使い方: https://kiwi-garakuta.pages.dev/tools/kiwi-transcribe/
問い合わせ: https://x.com/kiwi_dori のDM
ライセンス・著作権表示は同梱文書をご覧ください。
