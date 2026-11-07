#!/usr/bin/env python3
"""Run an explicitly selected model/build job in its own writable copy."""
import argparse
import json
from pathlib import Path
import signal
from model_private import JOBS, ROOT, encoded, run_model

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True, choices=JOBS)
    ap.add_argument('--phase', choices=['success', 'errors', 'concurrent'])
    ap.add_argument('--state-id')
    ap.add_argument('--timeout', type=int, default=55)
    ap.add_argument('--output-root', type=Path)
    args = ap.parse_args()
    output = (ROOT / args.output_root).absolute() if args.output_root is not None else None
    receipt = {}
    def cancelled(signum, frame):
        raise InterruptedError('Model controller signal ' + str(signum))
    signal.signal(signal.SIGTERM, cancelled)
    try:
        console = run_model(args.job, args.timeout, args.phase, args.state_id,
                            output_root=output, receipt=receipt)
        print(console, end='', flush=True)
    finally:
        if receipt:
            folder = ROOT / 'build/model-receipts'
            assert not folder.is_symlink()
            folder.mkdir(mode=0o700, exist_ok=True)
            path = folder / (Path(receipt['job']).name + '.json')
            with path.open('xb') as target:
                target.write(encoded(receipt) + b'\n')
            print('MODEL_RECEIPT ' + json.dumps(receipt, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
