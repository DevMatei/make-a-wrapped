import atexit
import shutil
import tempfile
from pathlib import Path

from wrapped_fm import badge_store, cluster, metrics, temp_artwork

_tmp = Path(tempfile.mkdtemp(prefix="wrapped-tests-"))
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
metrics.COUNTER_DB = _tmp / "counters.db"
metrics.WRAPPED_COUNT_FILE = _tmp / "wrapped-count.txt"
metrics.LEGACY_USES_FILE = _tmp / "template-uses.json"
cluster.CLUSTER_STATE_DIR = _tmp / "cluster"
temp_artwork.TEMP_ARTWORK_DIR = _tmp / "tmp-artwork"
badge_store.BADGE_SNAPSHOT_DIR = str(_tmp / "badges")
