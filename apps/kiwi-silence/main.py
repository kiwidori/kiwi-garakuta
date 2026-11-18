"""Desktop interface for a local recording's silent intervals."""
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
import core
from consumer_ui import Window


class App(Window):
    def __init__(self):
        super().__init__('きうい無音カット', '録音や動画の、音のない時間を短く。まず判定結果を確認して、別ファイルに保存します。', core.ENGINE)
        self.geometry('1080x730')
        self.minsize(940, 680)
        self.last_saved = None
        self.field('input', '元の録音・動画', picker=[('動画・音声', '*.mp4 *.mov *.mkv *.webm *.avi *.wav *.mp3 *.m4a *.flac *.ogg *.aac')])
        self.field('threshold', '無音とみなす音量（0.01～50 %）', '4')
        self.field('before', '声の前に残す余白（秒）', '0.2')
        self.field('after', '声の後に残す余白（秒）', '0.2')
        self.field('mincut', 'これより短い無音は残す（秒）', '0.2')
        self.field('silent', '無音部分の扱い', 'カットする', ['カットする', '早送りする'])
        self.field('profile', '保存形式', 'MP4（動画）', list(core.PROFILES))
        self.button(self.actions, '① 判定結果を確認', self.analyze).pack(side='left')
        self.button(self.actions, '② 別名で保存', self.render).pack(side='left', padx=8)
        self.button(self.actions, '保存先を開く', self.open_folder).pack(side='left')
        self.button(self.actions, '速度・音声・指定区間…', self.advanced).pack(side='right')
        self.extra = {key: tk.StringVar(value=value) for key, value in {
            'minclip': '0.1', 'speed': '1', 'silent_speed': '5', 'stream': 'all',
            'crf': '23', 'normalize': '変更しない', 'layout': '元のまま', 'ranges': ''}.items()}
        self.note.set('1ファイル512 MiB・60分まで。動画はフルHDまで。初回に公式Auto-Editor約46 MBを取得します。音声のみの入力はWAVかMP3を選択。小さい声まで消える場合はしきい値を下げてください。')
        self.show('① 判定結果で、残る時間と区間数を確認できます。\n② 保存時にも同じ設定で判定し直します。\n\n元のファイルは変更しません。同名ファイルがある場合は連番を付けます。')
        self.bind('<Alt-F4>', lambda event: (self.close(), 'break')[1])

    def options(self):
        values = self.values()
        values.update({k: v.get() for k, v in self.extra.items()})
        core.settings(values)
        return values

    def job(self, folder=None):
        if self.busy:
            return
        try:
            options = self.options()
            path = self.vars['input'].get()
            self.start(lambda: core.run(path, options, self.cancel, folder), self.done)
        except Exception as error:
            messagebox.showerror('設定を確認してください', str(error), parent=self)

    def done(self, result):
        self.show(result['text'])
        if result['saved']:
            self.last_saved = result['saved']
        self.status.set('保存しました。' if result['saved'] else '判定できました。設定を変えた場合はもう一度確認できます。')

    def analyze(self):
        self.job()

    def render(self):
        folder = self.choose_save()
        if folder:
            self.job(folder)

    def open_folder(self):
        if not self.busy and self.last_saved and Path(self.last_saved).is_file():
            os.startfile(str(Path(self.last_saved).parent))

    def advanced(self):
        if self.busy:
            return
        top = tk.Toplevel(self)
        top.title('速度・音声・指定区間')
        top.geometry('690x660')
        top.transient(self)
        top.grab_set()
        frame = ttk.Frame(top, padding=14)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        rows = [('speed', '通常部分の速度（0.5～3倍）', None),
                ('silent_speed', '無音の早送り速度（2～20倍）', None),
                ('minclip', 'これより短い発話を除く（秒）', None),
                ('stream', '判定に使う音声トラック（all＝すべて）', ['all', *map(str, range(10))]),
                ('crf', 'MP4の画質値（小さいほど高画質）', None),
                ('normalize', '音量の調整', ['変更しない', 'peak', 'ebu']),
                ('layout', '出力音声のチャンネル', ['元のまま', 'mono', 'stereo'])]
        for row, (key, label, choices) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=7)
            widget = ttk.Combobox(frame, textvariable=self.extra[key], values=choices, state='readonly') if choices else ttk.Entry(frame, textvariable=self.extra[key])
            widget.grid(row=row, column=1, sticky='ew', padx=(10, 0))
        ttk.Label(frame, text='指定区間（元ファイルの秒数・30行まで・重複不可）\n例：残す,0,2  または  削除,15,18').grid(row=7, column=0, columnspan=2, sticky='w', pady=(16, 6))
        text = tk.Text(frame, height=7, wrap='none')
        text.grid(row=8, column=0, columnspan=2, sticky='nsew')
        text.insert('1.0', self.extra['ranges'].get())
        ttk.Label(frame, text='残す指定は、その区間の速度を元の1倍に戻します。\n無音の早送り速度は「早送りする」を選んだ場合だけ使います。', wraplength=640).grid(row=9, column=0, columnspan=2, sticky='w', pady=10)
        def done():
            self.extra['ranges'].set(text.get('1.0', 'end-1c'))
            top.destroy()
        ttk.Button(frame, text='閉じる', command=done).grid(row=10, column=1, sticky='e')
        top.protocol('WM_DELETE_WINDOW', done)


if __name__ == '__main__':
    App().mainloop()
