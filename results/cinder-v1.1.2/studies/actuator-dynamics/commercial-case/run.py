from pathlib import Path
import shutil,subprocess,sys
HERE=Path(__file__).resolve().parent
def main():
    for name in ('derived','artifacts'):
        p=HERE/name
        if p.exists(): shutil.rmtree(p)
        p.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(HERE/'run_prescribed_transient.py')],check=True)
    return 0
if __name__=='__main__': raise SystemExit(main())
