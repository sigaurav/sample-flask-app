import logging
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
    
import schemas

log = logging.getLogger(__name__)


def main() -> None:
    result = schemas.get_pk("property")
    log.info(result)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()