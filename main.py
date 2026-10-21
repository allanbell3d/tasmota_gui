"""Android entry point.

python-for-android requires a ``main.py`` at the root of the packaged app
(see bootstraps/common/build/build.py: "No main.py(c) found in your app
directory"). Desktop users run ``python -m apps.desktop`` instead.
"""

from apps.mobile import main

if __name__ == "__main__":
    main()
