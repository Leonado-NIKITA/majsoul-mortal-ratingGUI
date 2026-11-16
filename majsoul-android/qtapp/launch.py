"""安卓构建 QT=1 时, 这个文件被复制成构建目录的 main.py (旧 main.py 改名 legacy_main.py)."""
import sys

from qtapp.main import main

if __name__ == "__main__":
    sys.exit(main())

