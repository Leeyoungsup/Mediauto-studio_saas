"""Bootstrap the installer-requested initial admin on an empty database.

Compatibility adapter for released application images: allow admin/admin only
in this bootstrap process. Normal account/password APIs retain their policy,
and the application's existing-user checks still prevent password resets.
"""
import os
from pathlib import Path
import sys


class InitialAdminPolicy:
    def __init__(self, original, login_id):
        self.original = original
        self.login_id = login_id

    def match(self, password):
        if self.login_id == 'admin' and password == 'admin':
            return True
        return self.original.match(password)


def main():
    # Both runners set the working directory to the application's backend.
    sys.path.insert(0, str(Path.cwd()))
    from scripts import bootstrap_runtime
    login_id = os.environ.get('MEDIAUTO_BOOTSTRAP_ADMIN_ID', '').strip().lower()
    bootstrap_runtime.STR_PASSWORD_PATTERN = InitialAdminPolicy(
        bootstrap_runtime.STR_PASSWORD_PATTERN, login_id)
    return bootstrap_runtime.main()


if __name__ == '__main__':
    sys.exit(main())
