from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
from runtime import resource_path
from workbench import launch
if __name__=='__main__':
    source=Path(__file__).resolve().parent
    launch(json.loads(Path(resource_path('profile.json',source)).read_text(encoding='utf-8')),source)
