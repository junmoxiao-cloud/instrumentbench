"""pytest 全局配置：把项目根加入 sys.path，使 `import judge.*` 在不安装包的情况下可用。

正式发布后（v0.1）改为 pip install -e . 可移除此 hack。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)
