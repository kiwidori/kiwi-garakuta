"""Write text as local synthetic speech."""
from pathlib import Path
import sys
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))

if __name__ == '__main__' and sys.argv[1:] == ['--speech-worker']:
    try:
        from speech_worker import run
        run()
    except Exception:
        raise SystemExit(2)
    raise SystemExit(0)

import gc
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import winsound
from consumer_ui import Window
from consumer_runtime import safe_path
import speech_core as core

LANG_NAMES = ['日本語', '英語', '韓国語', 'アラビア語', 'ブルガリア語', 'チェコ語', 'デンマーク語', 'ドイツ語', 'ギリシャ語', 'スペイン語', 'エストニア語', 'フィンランド語', 'フランス語', 'ヒンディー語', 'クロアチア語', 'ハンガリー語', 'インドネシア語', 'イタリア語', 'リトアニア語', 'ラトビア語', 'オランダ語', 'ポーランド語', 'ポルトガル語', 'ルーマニア語', 'ロシア語', 'スロバキア語', 'スロベニア語', 'スウェーデン語', 'トルコ語', 'ウクライナ語', 'ベトナム語']
LANG_CHOICES = [f'{name} ({code})' for name, code in zip(LANG_NAMES, core.LANGUAGES)]


class App(Window):
    def __init__(self):
        self.worker = None
        self.result = None
        super().__init__('きうい読み上げ', '文章をPC内で読み上げ音声に変換し、WAVで保存します。', None)
        self.geometry('1100x1000')
        self.minsize(960, 920)
        prepare = self.controls[0][0]
        prepare.configure(text='エンジンと音声モデルを準備（初回・約150 MiB）')
        terms = ttk.Frame(self.body)
        terms.pack(fill='x', pady=(0, 8), before=prepare)
        self.license_ack = tk.BooleanVar(value=False)
        ack = ttk.Checkbutton(terms, text='音声モデルのOpenRAIL-M利用条件に同意する', variable=self.license_ack)
        ack.pack(side='left')
        self.controls.append((ack, 'normal'))
        self.button(terms, '利用条件を読む', self.terms).pack(side='left', padx=12)
        source = ttk.LabelFrame(self.body, text='本文（300文字まで）', padding=8)
        source.pack(fill='x', pady=8, before=self.form)
        self.input = tk.Text(source, height=6, wrap='word', font=('Yu Gothic UI', 11))
        self.input.pack(fill='x')
        self.controls.append((self.input, 'normal'))
        self.button(source, 'UTF-8のテキストを開く', self.load_text).pack(anchor='w', pady=(5, 0))
        self.field('lang', '文章の言語', LANG_CHOICES[0], LANG_CHOICES)
        self.field('speaker', '声の種類（0〜9）', '0', [str(i) for i in range(10)])
        self.field('speed', '速さ（0.5〜2倍）', '1')
        self.field('steps', '品質の計算回数（2〜16）', '8', ['2', '4', '8', '12', '16'])
        self.field('threads', 'CPUスレッド数', '2', ['1', '2', '3', '4'])
        self.field('chunk', '文章の区切り', '標準', ['短め', '標準', '長め'])
        self.field('pause', '区切り間の無音（0〜2秒）', '0.3')
        self.field('seed', '乱数（-1は毎回変更、0以上で固定）', '-1')
        self.button(self.actions, 'WAVにして別名で保存', self.generate).pack(side='left')
        self.button(self.actions, '最後の音声を試聴', self.play).pack(side='left', padx=8)
        self.button(self.actions, '試聴を停止', self.stop_audio).pack(side='left')
        self.output.configure(height=4)
        self.note.set('本文300文字・音声90秒・処理90秒まで。初回準備後の変換はオフラインで、本文を送信しません。読み間違いがあります。音声を公開する場合は合成音声であることを示してください（モデル利用条件）。')
        self.status.set('本文と言語を選んでください。初回のみエンジンと音声モデルの準備が必要です。')

    def terms(self):
        top = tk.Toplevel(self)
        top.title('音声モデルの利用条件')
        top.geometry('930x650')
        ttk.Label(top, text='モデルの利用・出力の公開には以下のOpenRAIL-M利用条件が適用されます。第5条と付属書Aも確認してください。', wraplength=890).pack(padx=12, pady=12)
        box = tk.Text(top, wrap='word')
        box.pack(fill='both', expand=True, padx=12, pady=12)
        box.insert('1.0', (core.ROOT / 'MODEL-LICENSE.txt').read_text(encoding='utf8'))
        box.configure(state='disabled')

    def load_text(self):
        if self.busy:
            return
        name = filedialog.askopenfilename(parent=self, filetypes=[('UTF-8テキスト', '*.txt')])
        if not name:
            return
        try:
            path = safe_path(name)
            if not path.is_file() or path.stat().st_size > 32768:
                raise ValueError('32 KiB以内のテキストを選んでください。')
            text = path.read_text(encoding='utf-8-sig')
            if len(text) > 300:
                raise ValueError('本文は300文字以内です。使う部分をコピーして貼り付けてください。')
            self.input.delete('1.0', 'end')
            self.input.insert('1.0', text)
        except (ValueError, OSError) as error:
            messagebox.showerror('テキストを開けませんでした', str(error), parent=self)

    def allowed(self):
        if self.busy or self.closing:
            return False
        if not self.license_ack.get():
            self.status.set('音声モデルの利用条件を確認し、同意する場合はチェックしてください。')
            return False
        return True

    def setup(self):
        if not self.allowed():
            return
        self.start(lambda: core.install(self.cancel, lambda s: self.events.put(('status', s))),
                   lambda _: self.status.set('準備ができました。本文はPC内で音声に変換します。'))

    def generate(self):
        if not self.allowed():
            return
        try:
            v = self.values()
            v['lang'] = v['lang'].rsplit('(', 1)[-1].rstrip(')')
            v['chunk'] = {'短め': '40', '標準': '120', '長め': '300'}[v['chunk']]
            v['text'] = self.input.get('1.0', 'end-1c')
            v = core.options(v)
        except ValueError as error:
            self.status.set(str(error))
            return
        destination = self.choose_save()
        if not destination:
            return
        self.stop_audio()
        def done(result):
            self.result = result
            self.show('保存しました：' + result['path'] + f'\n長さ {result["seconds"]:.1f}秒 / 44.1 kHz・モノラル / 声 {result["speaker"]} / 言語 {result["lang"]}\n合成音声です。公開時にもそのことを示してください。')
            self.status.set('音声を保存しました。元のテキストと既存ファイルは変更していません。')
        self.start(lambda: core.generate(v, destination, self.cancel, lambda s: self.events.put(('status', s))), done)

    def play(self):
        if self.busy or not self.result:
            return
        try:
            path = safe_path(self.result['path'])
            core.validate_wave(path)
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (ValueError, OSError, RuntimeError) as error:
            self.status.set(str(error))

    def stop_audio(self):
        winsound.PlaySound(None, 0)

    def start(self, job, done):
        if self.busy or self.closing or self.worker and self.worker.is_alive():
            return
        gc.collect()
        self.busy = True
        self.cancel.clear()
        self.stop.configure(state='normal')
        for w, _ in self.controls:
            w.configure(state='disabled')
        def worker():
            try:
                self.events.put(('done', (done, job())))
            except Exception as error:
                self.events.put(('error', str(error)))
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                    continue
                self.busy = False
                self.stop.configure(state='disabled')
                for w, state in self.controls:
                    w.configure(state=state)
                if self.closing:
                    break
                if kind == 'error':
                    self.status.set(value[:300])
                    messagebox.showerror('処理できませんでした', value[:2500], parent=self)
                else:
                    done, result = value
                    done(result)
        except queue.Empty:
            pass
        if self.closing and not self.busy and not (self.worker and self.worker.is_alive()):
            self.destroy()
            return
        self.after(70, self.poll)

    def close(self):
        self.stop_audio()
        self.closing = True
        self.cancel.set()
        if not self.busy and not (self.worker and self.worker.is_alive()):
            self.destroy()

    def destroy(self):
        self.stop_audio()
        for timer in self.tk.splitlist(self.tk.call('after', 'info')):
            self.after_cancel(timer)
        super().destroy()
        self.vars.clear()
        self.license_ack = None
        gc.collect()


if __name__ == '__main__':
    App().mainloop()
