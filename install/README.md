# Windows development release

Extract the ZIP into a new directory. Python 3.11+ and internet access to install
the pinned packages are required. From PowerShell run `./install/windows.ps1`.
If Python is installed without the Windows launcher, use
`./install/windows.ps1 -Python C:/path/to/python.exe`.
Run `./.venv/Scripts/python.exe tools/run_dashboard.py` and sign in with the key printed
in that terminal. Stop with Ctrl+C. This is a foreground development installation,
not an unattended Windows service or a production surveillance deployment.
Optional OpenCV/model weights are excluded; default input and answers are synthetic.

The ZIP contains only an allow-listed wheel, public repository fixtures, tools and
documentation. It contains no local database, images, keys or model weights.
Compare manifest file hashes to detect accidental corruption; the manifest is not a
digital signature. Application licensing remains undecided. Review all dependency and
model licences separately before redistribution or commercial deployment.

For updates stop the old process, back up with `tools/release.py`, install to a new
directory and restore into a new working directory. Forward migration keeps a v2
database backup; rollback requires the previous app and that backup (new v3 data
will not exist there). Never open a v3 database with an old app or replace a running DB.
