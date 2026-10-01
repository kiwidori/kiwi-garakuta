"""Run one real added operation through an application's Tk window on Windows."""
from __future__ import annotations
import argparse
import ctypes
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('slug');args=parser.parse_args()
    ctypes.windll.user32.SetProcessDPIAware()
    sys.path.insert(0,str(ROOT/'apps'/args.slug))
    sys.path.insert(0,str(ROOT/'factory'))
    from verify_advanced import TOOLS
    from advanced_fixtures import CASES,PUBLIC
    from PIL import ImageGrab
    import main as gui
    app=gui.App();app.withdraw()
    controller=app.advanced
    controller.exe_path=str(ROOT/'.tools'/TOOLS[args.slug])
    controller.open_window()
    window=controller.toplevel
    window.geometry('1100x820+40+40');window.lift()
    app.update()
    assert len(controller.option_tree.get_children())==len(controller.spec['options'])
    argv,stdin,predicate=CASES[args.slug]
    argv=list(argv)
    if argv and argv[0] in controller.spec.get('subcommands',[]): controller.subcommand_var.set(argv.pop(0))
    for token in argv: controller._add_to_arg_tree(token)
    controller.stdin_text.insert('1.0',stdin.decode('utf8'))
    controller.cwd_var.set(str(PUBLIC));controller._update_preview()
    assert str(ROOT) not in controller.preview_text.get('1.0','end'), 'private executable path shown'
    controller._run()
    deadline=time.monotonic()+40
    while controller.running and time.monotonic()<deadline:
        app.update();time.sleep(.03)
    app.update()
    assert not controller.running,'GUI timed out'
    result=controller._last_result
    assert result and result['returncode']==0,controller.result_text.get('1.0','end')[:500]
    assert predicate(result['stdout']),args.slug
    assert controller.result_text.get('1.0','end').startswith('終了コード: 0')
    time.sleep(.15);app.update()
    screen=ROOT/'site/assets/screenshots'/f'{args.slug}-advanced-public.png'
    ImageGrab.grab(bbox=(window.winfo_rootx(),window.winfo_rooty(),window.winfo_rootx()+window.winfo_width(),window.winfo_rooty()+window.winfo_height())).save(screen)
    # Reopening must not reuse dead Text widgets or a previous result.
    controller._on_toplevel_close();app.update();controller.open_window();app.update()
    assert controller._last_result is None
    controller.preset_var.set(controller.spec['examples'][0]['name']);controller._on_preset_select()
    controller._run()
    deadline=time.monotonic()+40
    while controller.running and time.monotonic()<deadline:app.update();time.sleep(.03)
    app.update()
    assert controller._last_result and controller._last_result['returncode']==0,controller.result_text.get('1.0','end')[:500]
    controller._on_root_close()
    print('PASS:',args.slug,'advanced operation, preset, reopen, root close and public screenshot')

if __name__=='__main__':main()
