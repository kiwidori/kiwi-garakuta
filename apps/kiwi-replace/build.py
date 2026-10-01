from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
from portable_build import build
if __name__=='__main__': build(Path(__file__).resolve().parent)
