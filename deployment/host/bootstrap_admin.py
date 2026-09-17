"""Create the first administrator using the application's normal password policy.

Existing accounts are preserved by bootstrap_runtime; this never resets passwords.
"""
import os
from pathlib import Path
import sys


def main():
    # Older installer settings may still contain the obsolete short default.
    # This changes only the creation candidate, never an existing DB account.
    if (os.environ.get('MEDIAUTO_BOOTSTRAP_ADMIN_ID', '').lower() == 'admin'
            and os.environ.get('MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD') == 'admin'):
        os.environ['MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD'] = 'admin1234!'
        print('[INFO] Using updated initial password policy; existing accounts are not reset.', flush=True)
    sys.path.insert(0, str(Path.cwd()))
    from scripts import bootstrap_runtime
    return bootstrap_runtime.main()


if __name__ == '__main__':
    sys.exit(main())
