"""Render selected PDF pages with the original MuPDF command line engine."""
from pathlib import Path
import re
import sys
import tempfile
import zipfile
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import Engine, stage, save_file, check
from consumer_ui import Window

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = Engine(ROOT / "image-engine")


def page_list(value):
    result = []
    for part in value.replace(' ', '').split(','):
        if not re.fullmatch(r'[1-9]\d{0,3}(?:-[1-9]\d{0,3})?', part):
            raise ValueError('ページは「1-3,5」のように1～9999で指定してください。')
        ends = list(map(int, part.split('-')))
        first, last = ends[0], ends[-1]
        if first > last or last - first >= 100:
            raise ValueError('昇順、合計100ページ以内で指定してください。')
        result.extend(range(first, last + 1))
    result = list(dict.fromkeys(result))
    if not 1 <= len(result) <= 100:
        raise ValueError('合計100ページ以内で指定してください。')
    return result


def render(v, folder, cancel, preview=False):
    pages = page_list(v['pages'])
    if v['format'] not in {'PNG画像（ZIP）', 'テキスト'} or v['color'] not in {'カラー', 'グレー'}:
        raise ValueError('形式と色を選んでください。')
    dpi = int(v['dpi'])
    if not 36 <= dpi <= 300 or v['rotation'] not in {'0', '90', '180', '270'}:
        raise ValueError('解像度は36～300dpi、回転は0・90・180・270にしてください。')
    with tempfile.TemporaryDirectory(prefix='kiwi-pdf-images-') as td:
        work = Path(td)
        source = stage(v['input'], work, cancel, {'.pdf'}, limit=32 * 1024**2)
        raw_count = engine.call(['show', str(source), 'trailer/Root/Pages/Count'], work, cancel, timeout=30).strip()
        if not raw_count.isdigit() or not 1 <= int(raw_count) <= 100000:
            raise ValueError('PDFのページ数を確認できません。')
        if max(pages) > int(raw_count):
            raise ValueError(f'このPDFは{int(raw_count)}ページです。ページ指定を確認してください。')
        # No JavaScript interpreter or external viewers are invoked by mutool draw.
        fmt = 'txt' if not preview and v['format'] == 'テキスト' else 'png'
        pattern = work / ('page-%04d.png' if fmt == 'png' else 'text.txt')
        args = ['draw', '-q', '-F', fmt, '-o', str(pattern), '-m', '268435456', '-L', '-a']
        if fmt == 'png':
            args += ['-r', '72' if preview else str(dpi), '-w', '650' if preview else '3000',
                     '-h', '650' if preview else '3000', '-B', '64', '-T', '2', '-R', v['rotation'],
                     '-c', {'カラー': 'rgb', 'グレー': 'gray'}[v['color']]]
        args += [str(source), str(pages[0]) if preview else ','.join(map(str, pages))]
        engine.call(args, work, cancel, timeout=300)
        if preview:
            image = work / f'page-{pages[0]:04d}.png'
            return image.read_bytes()
        if fmt == 'txt':
            return str(save_file(pattern, folder, Path(v['input']).stem + '_text', '.txt', cancel))
        images = sorted(work.glob('page-*.png'))
        if len(images) != len(pages) or sum(p.stat().st_size for p in images) > 128 * 1024**2:
            raise ValueError('全ページを出力できませんでした。ページ指定を確認してください。')
        archive = work / 'images.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for image in images:
                check(cancel)
                z.write(image, image.name)
        return str(save_file(archive, folder, Path(v['input']).stem + '_pages', '.zip', cancel))
