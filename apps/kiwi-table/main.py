"""Organize local CSV tables through generated DuckDB queries."""
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import Engine, stage, save_file, check
from consumer_ui import Window

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = Engine(ROOT)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def read_table(value, work, cancel, encoding, delimiter):
    if encoding not in {'UTF-8', 'Shift_JIS'} or delimiter not in {'CSV', 'TSV'}:
        raise ValueError('文字コードと区切りを選んでください。')
    source = stage(value, work, cancel, {'.csv', '.tsv', '.txt'}, limit=16 * 1024**2)
    text = source.read_text(encoding='utf-8-sig' if encoding == 'UTF-8' else 'cp932')
    rows = csv.reader(io.StringIO(text, newline=''), delimiter=',' if delimiter == 'CSV' else '\t')
    try:
        names = next(rows)
    except StopIteration:
        raise ValueError('見出し行がありません。')
    if not 1 <= len(names) <= 100 or any(not n.strip() or '\x00' in n for n in names) or len({n.casefold() for n in names}) != len(names):
        raise ValueError('見出しは1～100列、空欄・重複なしにしてください。')
    out = work / 'normalized.csv'
    count = 0
    with out.open('w', encoding='utf8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(names)
        for row in rows:
            check(cancel)
            count += 1
            if count > 100000 or len(row) != len(names) or any('\x00' in cell or len(cell) > 100000 for cell in row):
                raise ValueError('10万行まで、各行の列数を見出しに合わせてください。セルは10万文字までです。')
            writer.writerow(row)
    if out.stat().st_size > 32 * 1024**2:
        raise ValueError('UTF-8変換後の表が32 MiBを超えました。')
    return out, names, count


def transform(v, folder, cancel, preview=False, headings=False):
    with tempfile.TemporaryDirectory(prefix='kiwi-table-') as td:
        work = Path(td)
        source, names, count = read_table(v['input'], work, cancel, v['encoding'], v['delimiter'])
        if headings:
            return names, count
        columns = [n.strip() for n in v.get('columns', '').split('\n') if n.strip()] or names
        if any(n not in names for n in columns) or len(set(columns)) != len(columns):
            raise ValueError('出力列は「列を確認」から1行に1列ずつ指定してください。')
        conditions = []
        field = v.get('filter_column', '')
        if field:
            if field not in names:
                raise ValueError('絞り込み列を確認してください。')
            c, x = identifier(field), literal(v.get('filter_value', ''))
            mode = v['filter_mode']
            if mode == '含む':
                conditions.append(f'contains(coalesce({c},\'\'), {x})')
            elif mode == '一致':
                conditions.append(f'coalesce({c},\'\') = {x}')
            elif mode == '以上（数値）':
                conditions.append(f'try_cast({c} AS DOUBLE) >= try_cast({x} AS DOUBLE)')
            elif mode == '以下（数値）':
                conditions.append(f'try_cast({c} AS DOUBLE) <= try_cast({x} AS DOUBLE)')
            else:
                raise ValueError('絞り込み方法を選んでください。')
        if v.get('blank') == '取り除く':
            conditions.append('(' + ' OR '.join(f"coalesce(trim({identifier(n)}),'') <> ''" for n in columns) + ')')
        query = 'SELECT ' + ('DISTINCT ' if v.get('dedupe') == '取り除く' else '') + ','.join(map(identifier, columns))
        query += f' FROM read_csv({literal(source.as_posix())},header=true,all_varchar=true,nullstr=\'\',parallel=false)'
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        order = v.get('sort_column', '')
        if order:
            if order not in columns:
                raise ValueError('並べ替え列は出力列に含めてください。')
            expression = identifier(order)
            if v.get('numeric') == '数値':
                expression = f'try_cast({expression} AS DOUBLE)'
            query += ' ORDER BY ' + expression + (' DESC' if v.get('direction') == '降順' else ' ASC') + ' NULLS LAST'
        fmt = v['format']
        if fmt not in {'CSV', 'TSV', 'JSON'}:
            raise ValueError('保存形式を選んでください。')
        output = work / ('result.' + ('json' if fmt == 'JSON' else 'csv' if fmt == 'CSV' else 'tsv'))
        settings = "SET autoinstall_known_extensions=false; SET autoload_known_extensions=false; SET threads=2; SET memory_limit='256MB'; SET preserve_insertion_order=true;"
        if preview:
            sql = settings + query + ' LIMIT 100;'
        else:
            options = 'FORMAT JSON, ARRAY true' if fmt == 'JSON' else f"FORMAT CSV, HEADER true, DELIMITER {literal(chr(9) if fmt == 'TSV' else ',')}"
            sql = settings + f'COPY ({query}) TO {literal(output.as_posix())} ({options});'
        raw = engine.call(['-no-agent', '-no-init', '-batch', '-bail', '-json', ':memory:'], work, cancel, stdin=sql.encode('utf8'))
        if preview:
            return json.loads(raw or b'[]'), names, count
        if output.stat().st_size > 64 * 1024**2:
            raise ValueError('出力が64 MiBを超えました。')
        # UTF-8 BOM makes CSV readable in Windows spreadsheet applications.
        if fmt in {'CSV', 'TSV'}:
            output.write_bytes(b'\xef\xbb\xbf' + output.read_bytes())
        return str(save_file(output, folder, Path(v['input']).stem + '_organized', output.suffix, cancel))


class App(Window):
    def __init__(self):
        super().__init__('きういCSV整理', '住所録・家計簿・一覧表の列選び、絞り込み、並べ替え。元のCSVには書き込みません。', engine)
        self.field('input', 'CSV・TSV', picker=[('表', '*.csv *.tsv *.txt')])
        self.field('encoding', '文字コード', 'UTF-8', ['UTF-8', 'Shift_JIS'])
        self.field('delimiter', '入力の区切り', 'CSV', ['CSV', 'TSV'])
        self.field('columns', '出力列（選択ボタンで指定）')
        column_widget = self.controls[-1][0]
        column_widget.configure(state='readonly')
        self.controls[-1] = (column_widget, 'readonly')
        self.field('filter_column', '絞り込み列（空欄でなし）')
        self.field('filter_mode', '絞り込み方法', '含む', ['含む', '一致', '以上（数値）', '以下（数値）'])
        self.field('filter_value', '絞り込む値')
        self.field('sort_column', '並べ替え列（空欄でなし）')
        self.field('numeric', '並べ替えの種類', '文字', ['文字', '数値'])
        self.field('direction', '順序', '昇順', ['昇順', '降順'])
        self.field('dedupe', '同じ内容の行', '残す', ['残す', '取り除く'])
        self.field('blank', '全列が空白の行', '残す', ['残す', '取り除く'])
        self.field('format', '保存形式', 'CSV', ['CSV', 'TSV', 'JSON'])
        self.geometry('1080x950')
        self.button(self.actions, '列を確認・選択', self.columns).pack(side='left')
        self.button(self.actions, '先頭100行を確認', self.preview).pack(side='left', padx=8)
        self.button(self.actions, '整理して保存…', self.save).pack(side='left')
        self.note.set('入力16 MiB・10万行・100列まで。先頭行は見出し必須です。保存はUTF-8。数式は実行しませんが、保存CSVを表計算ソフトで開く際はそのソフトの安全設定に従ってください。')

    def values(self):
        v = super().values()
        v['columns'] = '\n'.join(getattr(self, 'selected_columns', []))
        return v

    def columns(self):
        v = self.values()
        def show(result):
            import tkinter as tk
            from tkinter import ttk
            names, count = result
            top = tk.Toplevel(self)
            top.title('出力する列を選択')
            ttk.Label(top, text=f'{count:,}行 / {len(names)}列。Ctrl・Shiftで複数選択できます。').pack(padx=15, pady=10)
            box = tk.Listbox(top, selectmode='extended', width=45, height=min(20, len(names)), exportselection=False)
            box.pack(padx=15, pady=8)
            for n in names:
                box.insert('end', n)
            box.selection_set(0, 'end')
            def accept():
                self.selected_columns = [names[i] for i in box.curselection()]
                self.vars['columns'].set(' / '.join(self.selected_columns))
                top.destroy()
            ttk.Button(top, text='この列を使う', command=accept).pack(pady=10)
            self.show('\n'.join(names) + f'\n\n全 {count:,} 行')
        self.start(lambda: transform(v, None, self.cancel, headings=True), show)

    def preview(self):
        v = self.values()
        def show(result):
            rows, _, count = result
            # Tab-separated plain text remains selectable and never evaluates CSV cells.
            keys = list(rows[0]) if rows else []
            lines = ['\t'.join(keys)] + ['\t'.join(str(row[k] or '').replace('\n', ' ↵ ') for k in keys) for row in rows]
            self.show(f'入力 {count:,} 行 / 結果の先頭 {len(rows)} 行\n\n' + '\n'.join(lines))
            self.status.set('先頭100行までを表示しました。')
        self.start(lambda: transform(v, None, self.cancel, True), show)

    def save(self):
        folder = self.choose_save()
        if folder:
            v = self.values()
            self.start(lambda: transform(v, folder, self.cancel), lambda p: (self.show('保存しました。\n' + p), self.status.set('保存できました。')))


if __name__ == '__main__':
    App().mainloop()
