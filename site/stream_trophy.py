"""Participation guide for the stream trophy extension."""
from html import escape


def content(settings):
    config = settings['stream_trophy']
    download = escape(config['download_url'], quote=True)
    privacy = escape(config['privacy_url'], quote=True)
    contact = escape(settings['contact_url'], quote=True)
    store = config.get('store_url')
    store_notice = (f'<p><a class="button button-secondary" href="{escape(store, quote=True)}" rel="noopener noreferrer">Chromeウェブストアで開く ↗</a></p>'
                    if store else '<p>Chromeウェブストアで公開準備中です。現在はZIPを展開して、手動で読み込む方法をご案内しています。</p>')
    return f'''<nav class="crumb" aria-label="パンくず"><a href="/">ホーム</a><span>/</span><span>配信トロフィー</span></nav>
<section class="guide-hero"><div class="eyebrow">配信に参加する · 配信トロフィー</div><h1>コメントも、いっしょの時間も、<br>トロフィーに。</h1><p class="lead">きういのYouTube配信で、コメントしたり配信を見たりすると、<br>あなただけのトロフィーが集まります。</p><a class="button" href="{download}" download>拡張のZIPをダウンロード</a><p>PCのChrome・Edge向け · バージョン1.0.0 · 約11KB</p></section>
<nav class="page-nav" aria-label="ページの内容"><a href="#join">参加のしかた</a><a href="#install">拡張の入れ方</a><a href="#commands">チャットコマンド</a><a href="#questions">よくある質問</a><a href="#privacy">データの取り扱い</a></nav>
<div class="guide-content">
<section class="content-section" id="join"><h2>参加のしかたは、2通り</h2><div class="guide-points"><article><h3>コメントするだけ</h3><p>配信チャットのコメント数・総文字数・参加した配信の数・メンバーシップに応じて、トロフィーが集まります。スマホからのコメントも対象です。拡張の準備は必要ありません。</p></article><article><h3>視聴時間も集める（PCのみ）</h3><p>PCのChromeかEdgeに拡張を入れて連携すると、ライブ配信を見ていた時間も記録されます。自分のトロフィー図鑑も開けます。</p></article></div><p>専用のGoogleログインやアカウント連携の許可画面はありません。合言葉の投稿には、普段のYouTubeチャットを使います。</p></section>
<section class="content-section" id="install"><h2>拡張の入れ方</h2>{store_notice}<ol class="steps">
<li><span><strong>ZIPをダウンロードする</strong>このページのボタンから <code>stream-trophy-extension.zip</code> を保存します。</span></li>
<li><span><strong>ZIPをすべて展開する</strong>ZIPを右クリックして「すべて展開」を選びます。展開したフォルダーは、拡張を使う間は消さずに置いておきます。</span></li>
<li><span><strong>拡張の管理画面を開く</strong>Chromeのアドレス欄に <code>chrome://extensions</code> と入力します。Edgeでは <code>edge://extensions</code> です。</span></li>
<li><span><strong>デベロッパーモードをオンにする</strong>拡張の管理画面にある「デベロッパーモード」のスイッチをオンにします。</span></li>
<li><span><strong>展開したフォルダーを読み込む</strong>「パッケージ化されていない拡張機能を読み込む」を選び、<code>manifest.json</code> が入っているフォルダーを指定します。</span></li>
<li><span><strong>合言葉をライブチャットに書く</strong>開いた案内ページの <code>!link 123456</code> のような合言葉を、きういのライブ配信中のチャットへ1回送ります。数字は自分の画面に表示されたものを使ってください。</span></li>
<li><span><strong>連携できたことを確認する</strong>拡張の表示が「○○ さんのコレクション」に変われば完了です。連携した名前を確認して、いつも通り配信をお楽しみください。</span></li>
</ol><a class="button" href="{download}" download>ZIPをダウンロード</a><p>合言葉は15分有効です。期限が切れたら「新しい合言葉を発行」から出し直せます。読み込み後に配信ページを開き直すと、計測を始められます。</p><p>手動で入れた拡張について、ブラウザーから確認が表示される場合があります。名前・配布元・権限を確認し、不明な場合は読み込みを中止してください。</p></section>
<section class="content-section" id="commands"><h2>チャットコマンド</h2><p>きういのライブ配信中のチャットに書き込みます。</p><div class="guide-points"><article><h3><code>!link 123456</code></h3><p>拡張と連携します。数字は拡張に表示された合言葉に置き換えます。</p></article><article><h3><code>!trophy off</code></h3><p>自分の記録・トロフィー・連携を削除し、以後の記録を止めます。</p></article><article><h3><code>!trophy on</code></h3><p>記録を再開します。削除前の記録は戻りません。</p></article></div></section>
<section class="content-section faq" id="questions"><h2>よくある質問</h2>
<details><summary>参加しないといけませんか？</summary><p>参加は任意です。記録されたくない場合は、ライブチャットに <code>!trophy off</code> と書いてください。拡張を入れなくても、配信は今まで通り楽しめます。</p></details>
<details><summary>スマホやテレビで見た時間も記録されますか？</summary><p>視聴時間は拡張を入れたPCのブラウザーで見た分だけが対象です。スマホのYouTubeアプリやテレビで見た時間は記録されません。スマホからのコメントは対象です。</p></details>
<details><summary>どんなときに視聴時間が増えますか？</summary><p>対象のライブ配信を再生している間です。一時停止中・広告中・読み込み中・アーカイブは対象外です。倍速で見ても、実際の時間以上には増えません。拡張のスイッチで視聴時間の記録を止められます。</p></details>
<details><summary>複数のタブで開くと二重に増えますか？</summary><p>複数のタブで見ても、同じ人の視聴時間が二重に増えない仕組みです。</p></details>
<details><summary>トロフィーを取ったらどうなりますか？</summary><p>表示名とトロフィー名が配信画面に表示される場合があります。</p></details>
<details><summary>自分のトロフィーはどこで見られますか？</summary><p>拡張のアイコンを押して「トロフィー図鑑を開く」を選びます。</p></details>
<details><summary>拡張をやめたいときは？</summary><p>拡張の「自分の記録をすべて削除」を実行してから、拡張の管理画面で削除してください。削除後にもう一度合言葉で連携すると記録が再開するため、やめる場合は再連携しないでください。</p></details>
</section>
<section class="content-section" id="privacy"><h2>データの取り扱い</h2><ul class="feature-list"><li>チャットに公開されているチャンネルID・表示名・メンバーかどうか、コメントの件数・総文字数、参加した配信の数・視聴時間・獲得トロフィーを記録します。</li><li><strong>コメント本文は保存しません。</strong>重複集計を防ぐ投稿IDは3日で自動削除します。</li><li>Googleアカウントのメールアドレス・登録チャンネル・視聴履歴にはアクセスしません。</li><li>拡張は対象のライブ配信の動画ID・計測時間・タブごとのランダムID・計測順序を示す値を、連携用トークンを使って送信します。他の動画・検索・閲覧履歴は送りません。</li><li>記録はCloudflare上に保管します。トロフィーの獲得時は、表示名とトロフィー名が配信画面に表示される場合があります。</li><li><code>!trophy off</code> または拡張の削除ボタンで記録を削除できます。拡張のスイッチをオフにするだけでは、既存の記録は削除されません。</li></ul><a class="textlink" href="{privacy}" rel="noopener noreferrer">データの取り扱いを詳しく読む ↗</a></section>
<section class="content-section" id="contact"><h2>うまく動かないときは</h2><p>どの手順で、どんな表示が出たかを添えて、XのDMへお寄せください。</p><a class="button button-secondary" href="{contact}" rel="noopener noreferrer">Xで @kiwi_dori を開く ↗</a></section>
</div>'''
