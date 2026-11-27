#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    # The test suite never touches the catalog database or a running Postgres.
    if "test" in sys.argv[1:]:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "catalog.settings.test")
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "catalog.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
