"""Preview-first, single-folder file renaming through F2."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import Engine, safe_path, check
from consumer_ui import Window
from tkinter import messagebox

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = Engine(ROOT)


def filename(name):
    return (bool(name) and len(name) <= 200 and name not in {'.', '..'} and
            not name.endswith((' ', '.')) and not re.search(r'[<>:"/\\|?*{}\x00-\x1f]', name) and
            not re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I))


def fingerprint(path, cancel):
    p = safe_path(path)
    if not p.is_file():
        raise ValueError('通常のファイルだけを指定してください。')
    s = p.stat()
    if s.st_size > 256 * 1024**2:
        raise ValueError('1件256 MiB以下のファイルを指定してください。')
    h = hashlib.sha256()
    with p.open('rb') as f:
        while chunk := f.read(1024**2):
            check(cancel)
            h.update(chunk)
    return [s.st_size, s.st_mtime_ns, h.hexdigest()]


def preview(v, cancel):
    folder = safe_path(v['folder'], True)
    files = []
    total = 0
    for p in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if p.is_dir():
            continue
        p = safe_path(p)
        if not p.is_file() or p.name.startswith('.') or getattr(p.stat(), 'st_file_attributes', 0) & 2:
            continue
        total += p.stat().st_size
        files.append(p)
        if len(files) > 500 or total > 2 * 1024**3:
            raise ValueError('1フォルダー500件・合計2 GiBまでです。')
    if not files:
        raise ValueError('対象の通常ファイルがありません。')
    if v['method'] not in {'文字を置換', '正規表現で置換', '連番にする'}:
        raise ValueError('変更方法を選んでください。')
    if any(c in v['replace'] for c in '{}') or len(v['find']) > 200 or len(v['replace']) > 150:
        raise ValueError('置換文字に波括弧は使えません。検索200文字・置換150文字までです。')
    args = ['--json', '--no-color', '--ignore-ext', '--sort', 'natural']
    if v['method'] == '連番にする':
        if not v['replace'].strip():
            raise ValueError('連番の前に付ける名前を入力してください。')
        args += ['--find', '^.*$', '--replace', v['replace'] + '_{%03d}']
    else:
        if not v['find']:
            raise ValueError('検索する文字を入力してください。')
        args += ['--find', v['find'], '--replace', v['replace']]
        if v['method'] == '文字を置換':
            args.append('--string-mode')
    if v['case'] == '区別しない':
        args.append('--ignore-case')
    args += ['--', *map(str, files)]
    with tempfile.TemporaryDirectory(prefix='kiwi-rename-plan-') as td:
        work = Path(td)
        rows = json.loads(engine.call(args, work, cancel) or b'[]')
    plan = []
    targets = set()
    for row in rows:
        if row.get('status') != 'ok' or row.get('is_dir') or not filename(row['source']) or not filename(row['target']):
            raise ValueError('変更先が不正か、名前が重複しています。設定を変更してください。')
        source = safe_path(Path(row['base_dir']) / row['source'])
        dest = safe_path(Path(row['target_dir']) / row['target'])
        if source.parent != folder or dest.parent != folder or source not in files:
            raise ValueError('対象フォルダー外への変更はできません。')
        if source == dest:
            continue
        if source.name.casefold() == dest.name.casefold() or dest.exists() or dest.name.casefold() in targets:
            raise ValueError('変更先に同名ファイルがあります。大文字・小文字だけの変更にも対応していません。')
        targets.add(dest.name.casefold())
        plan.append({'source': str(source), 'target': str(dest), 'fingerprint': fingerprint(source, cancel)})
    if not plan:
        raise ValueError('変更するファイルがありません。')
    return plan


def apply(plan, cancel, undo=False):
    if not plan or len(plan) > 500:
        raise ValueError('先に変更予定を確認してください。')
    pairs = []
    for row in plan:
        source = safe_path(row['target'] if undo else row['source'])
        dest = safe_path(row['source'] if undo else row['target'])
        if source.parent != dest.parent or dest.exists() or fingerprint(source, cancel) != row['fingerprint']:
            raise ValueError('ファイルまたは変更先が変わりました。再度プレビューしてください。')
        pairs.append((source, dest))
    journal = safe_path(engine.cache.parent / 'last-change.json')
    journal.parent.mkdir(parents=True, exist_ok=True)
    if not undo:
        # Keep a recovery record even if the process is cancelled or only partly completes.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=journal.parent, delete=False) as f:
            temporary = Path(f.name)
            json.dump(plan, f, ensure_ascii=False)
        try:
            os.replace(temporary, journal)
        finally:
            temporary.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix='kiwi-rename-apply-') as td:
        work = Path(td)
        csv_path = work / 'plan.csv'
        with csv_path.open('w', encoding='utf8', newline='') as f:
            csv.writer(f).writerows((str(a), b.name) for a, b in pairs)
        # F2 reads only these explicit pairs. No recursive search or automatic conflict fixing.
        engine.call(['--csv', str(csv_path), '--json', '--no-color', '--exec'], work, cancel, timeout=300)
    for row, (source, dest) in zip(plan, pairs):
        if source.exists() or not dest.is_file() or fingerprint(dest, cancel) != row['fingerprint']:
            raise ValueError('一部の結果を確認できませんでした。フォルダーを確認してください。')
    if undo:
        journal.unlink(missing_ok=True)
    return plan


def recover(cancel):
    journal = safe_path(engine.cache.parent / 'last-change.json')
    if not journal.is_file() or journal.stat().st_size > 2 * 1024**2:
        raise ValueError('元に戻せる変更記録がありません。')
    plan = json.loads(journal.read_text(encoding='utf8'))
    if not isinstance(plan, list) or len(plan) > 500:
        raise ValueError('変更記録を確認できません。')
    changed = []
    for row in plan:
        source, target = safe_path(row['source']), safe_path(row['target'])
        if source.parent != target.parent or not filename(source.name) or not filename(target.name):
            raise ValueError('変更記録のパスを確認できません。')
        if target.exists() and not source.exists() and fingerprint(target, cancel) == row['fingerprint']:
            changed.append(row)
        elif source.exists() and not target.exists() and fingerprint(source, cancel) == row['fingerprint']:
            continue
        else:
            raise ValueError('変更後にファイルが移動・編集されています。自動では元に戻せません。')
    if not changed:
        raise ValueError('元に戻す必要のある変更がありません。')
    return apply(changed, cancel, True)


class App(Window):
    def __init__(self):
        super().__init__('きうい名前整理', '写真や書類のファイル名をまとめて整理。変更前・変更後を見比べてから実行します。', engine)
        self.plan = None
        self.undo_plan = None
        self.field('folder', '対象フォルダー', picker='folder')
        self.field('method', '変更方法', '文字を置換', ['文字を置換', '正規表現で置換', '連番にする'])
        self.field('find', '検索する文字')
        self.field('replace', '置換文字・連番の名前')
        self.field('case', '英字の大文字・小文字', '区別する', ['区別する', '区別しない'])
        for v in self.vars.values():
            v.trace_add('write', lambda *_: self.invalidate())
        self.button(self.actions, '変更予定を見る', self.preview).pack(side='left')
        self.button(self.actions, '確認した変更を実行', self.execute).pack(side='left', padx=10)
        self.button(self.actions, '直前の変更を元に戻す', self.undo).pack(side='left')
        self.note.set('サブフォルダー・隠しファイル・拡張子は変更しません。500件・各256 MiB・合計2 GiBまで。直前の変更記録は終了後も保持します。停止時は一部だけ変更される場合があります。大切なファイルは先にバックアップしてください。')
        self.show('「文字を置換」例：DSC → 旅行\n「連番にする」例：名前に「旅行」を指定 → 旅行_001.jpg\n既存ファイルの上書きやフォルダーの移動は行いません。')

    def invalidate(self):
        self.plan = None

    def preview(self):
        v = self.values()
        self.plan = None
        def done(plan):
            self.plan = plan
            self.show('\n'.join(f'{Path(p["source"]).name}  →  {Path(p["target"]).name}' for p in plan))
            self.status.set(f'{len(plan)}件の変更予定です。内容を確認してください。')
        self.start(lambda: preview(v, self.cancel), done)

    def execute(self):
        if self.busy:
            return
        if not self.plan:
            messagebox.showinfo('先に確認してください', '「変更予定を見る」を押して内容を確認してください。', parent=self)
            return
        plan = self.plan
        if not messagebox.askyesno('ファイル名を変更', f'表示中の{len(plan)}件の名前を変更しますか？', parent=self):
            return
        self.plan = None
        def done(result):
            self.undo_plan = result
            self.status.set(f'{len(result)}件の名前を変更しました。')
            self.show('変更しました。\n' + '\n'.join(Path(p['target']).name for p in result))
        self.start(lambda: apply(plan, self.cancel), done)

    def undo(self):
        if self.busy:
            return
        if not messagebox.askyesno('元に戻す', '直前の変更を元に戻しますか？', parent=self):
            return
        self.undo_plan = None
        self.plan = None
        self.start(lambda: recover(self.cancel), lambda result: (self.show('元の名前に戻しました。'), self.status.set(f'{len(result)}件を元に戻しました。')))


if __name__ == '__main__':
    App().mainloop()
