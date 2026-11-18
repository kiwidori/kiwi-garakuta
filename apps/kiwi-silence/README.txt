きうい無音カット 0.1.0 — Windows 11 x64

録音や動画から無音部分を取り除き、別のファイルに保存します。
1. ZIPをすべて展開し、KiwiSilence.exeを起動します。
2. 初回だけ「エンジンを準備」で公式Auto-Editor 31.9.0（約46 MB）を取得します。
3. ファイルを選び、「判定結果を確認」で残る時間を確認します。
4. 保存形式を選び、「別名で保存」で保存先フォルダーを指定します。
音声のみの入力はWAVかMP3で保存してください。

小さい声が消える場合は無音のしきい値を下げてください。
前後の余白、短い無音の扱い、早送り・通常速度、音量調整、トラック選択、
元ファイルの秒数を使った残す／削除区間を設定できます。
判定は音量によるものです。発言内容の理解や雑音の除去は行いません。
保存時に同じ設定で再判定します。保存前に再生する機能はありません。
元ファイルは変更せず、同名の出力には連番を付けます。
停止すると処理中の出力を破棄します。すでに保存したファイルは残ります。

入力：WAV/MP3/M4A/FLAC/OGG/AAC/MP4/MOV/MKV/WebM/AVIの単一ローカルファイル。
音声トラック必須、512 MiB・60分以内。動画は長辺1920・短辺1080まで。
出力：MP4（H.264/AAC）、WAV（PCM16）、MP3（192 kbps）。
WAV・MP3は複数の音声トラックを1本に混ぜて保存します。
処理は15分・実行グループ2 GiBまで。長い動画は先に短く分割してください。
字幕・データトラックは保存しません。複数ファイル同時処理、編集ソフト用
タイムライン出力、録音、URL取得、追加エフェクトはありません。

エンジンはこのZIPに同梱せず、公式固定版をSHA-256検証して取得します。
準備後のメディア処理はPC内で行い、ファイルをアップロードしません。
Auto-EditorのコードはUnlicenseですが、公式実行ファイルに含まれる
FFmpeg等の依存物にはそれぞれのライセンスが適用されます。
本ソフトは公式バイナリやライセンス判定を改変せず、キー入力を提供しません。
本GUIとAuto-Editorは別のプロジェクトです。
上流：https://github.com/WyattBlue/auto-editor
固定版ソース：https://github.com/WyattBlue/auto-editor/tree/31.9.0
ビルド情報：https://github.com/WyattBlue/auto-editor/blob/31.9.0/ae.nimble
GUIソース：https://github.com/kiwidori/kiwi-garakuta/tree/main/apps/kiwi-silence
サイト：https://kiwi-garakuta.pages.dev/tools/kiwi-silence/
問い合わせ：https://x.com/kiwi_dori
