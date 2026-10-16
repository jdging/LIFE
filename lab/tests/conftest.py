import sys
from pathlib import Path

# Los tests del backend v2 (t_65096083) hacen `import db` directo; exponer lab/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
