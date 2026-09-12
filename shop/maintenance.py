"""Run expiry maintenance without starting an inference worker."""
import argparse
import logging
import time

from shop.work_queue import expire


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Expire due work and exit (suitable for a scheduled job)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    while True:
        count = expire()
        if count:
            logging.getLogger("shop.maintenance").info("expired_count=%s", count)
        if count == 100:
            continue
        if args.once:
            return
        time.sleep(1)


if __name__ == "__main__":
    main()
