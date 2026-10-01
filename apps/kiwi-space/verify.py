"""Check real capacity snapshot against Windows and exercise the GUI."""
import csv
import ctypes
import importlib.util
import io
import json
import sys
import threading
import time
from pathlib import Path
from PIL import ImageGrab
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import core

def wait(app):
    deadline=time.monotonic()+20
    while app.running and time.monotonic()<deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running

def main():
    exe=ROOT/'.tools/duf/duf.exe'
    rows=core.read_drives(exe,threading.Event())
    current=next(row for row in rows if row['drive']=='C:\\')
    free,total,totalfree=(ctypes.c_ulonglong() for _ in range(3))
    assert ctypes.windll.kernel32.GetDiskFreeSpaceExW('C:\\',ctypes.byref(free),ctypes.byref(total),ctypes.byref(totalfree))
    assert current['total']==total.value
    assert abs(current['free']-totalfree.value)<512*1024*1024
    assert abs(current['used']+current['free']-current['total'])<4096
    sample={'device_type':'local','mount_point':'C:\\','fs_type':'NTFS','total':1000,'used':750,'free':250,'device':'private-label'}
    parsed=core.parse_drives(json.dumps([sample]))
    assert parsed==[{'drive':'C:\\','filesystem':'NTFS','total':1000,'used':750,'free':250,'usage':75.0}]
    assert 'private-label' not in str(parsed)
    for bad in ('{}','broken','[null]',json.dumps([dict(sample,total=-1)]),json.dumps([dict(sample,free=True)]),json.dumps([dict(sample,used=1001)])):
        try:
            core.parse_drives(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Bad capacity data accepted')
    data=core.csv_bytes(rows)
    assert data.startswith(b'\xef\xbb\xbf')
    table=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    assert int(table[0]['total_bytes'])==rows[0]['total']
    original=core.subprocess.Popen
    children=[]
    def slow_child(_cmd,**kwargs):
        child=original([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
        children.append(child)
        return child
    core.subprocess.Popen=slow_child
    event=threading.Event()
    timer=threading.Timer(0.2,event.set)
    timer.start()
    try:
        core.read_drives(exe,event)
    except InterruptedError:
        assert children and children[0].poll() is not None
    else:
        raise AssertionError('Cancellation ignored')
    finally:
        timer.cancel()
        core.subprocess.Popen=original
    spec=importlib.util.spec_from_file_location('kiwi_space',HERE/'main.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.resource_dir=lambda:exe.parent
    app=module.App()
    try:
        app.update()
        time.sleep(0.2)
        app.update()
        app.refresh()
        wait(app)
        assert app.rows and len(app.tree.get_children())==len(app.rows),app.status.get()
        app.sort_column('free')
        assert [row['free'] for row in app.rows]==sorted(row['free'] for row in app.rows)
        app.tree.selection_set(app.tree.get_children()[0])
        app.copy_selected()
        assert app.rows[0]['drive'] in app.clipboard_get()
        folder=Path('C:/Users/Public/Documents/kiwi-space-demo')
        folder.mkdir(exist_ok=True)
        path=folder/'容量一覧.csv'
        module.filedialog.asksaveasfilename=lambda **kwargs:str(path)
        app.save_csv()
        assert path.read_bytes()==core.csv_bytes(app.rows)
        app.status.set('取得完了（手動更新）')
        app.geometry('1000x500+100+100')
        app.attributes('-topmost',True)
        app.update()
        app.lift()
        time.sleep(0.3)
        x,y=app.winfo_rootx(),app.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-space-public.png')
        def slow_read(_exe,event):
            assert event.wait(5)
            raise InterruptedError()
        module.read_drives=slow_read
        app.refresh()
        app.update()
        app.stop()
        wait(app)
        assert '停止' in app.status.get()
    finally:
        app.close()
    print('PASS: real Windows capacity cross-check, privacy filtering, JSON validation, CSV bytes, child cancellation, GUI refresh/sort/copy/save/stop')

if __name__=='__main__':
    main()
