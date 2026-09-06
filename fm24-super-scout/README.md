# FM24 Super Scout

A local, read-only scouting viewer for Football Manager 2024. It is a separate
project from `fm-project` and is designed around repeatable snapshots:

- import FM24 HTML/CSV exports or JSON dumps;
- calculate best-position and role scores;
- filter by name, club, position, age, CA, PA and value;
- mark players on a shortlist and export it to CSV;
- compare current snapshots with an earlier snapshot to show CA growth.

## Run

```powershell
cd fm24-super-scout
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8765`. Put exports in `snapshots/`, or use the file
picker in the app. The loader accepts the FM24 Python Export table shape and a
JSON list/object with a `players` or `data` list.

## Read-only FM24 memory capture

For FM24 build 24.4.2, the project includes an experimental Windows memory
dumper based on the documented person-table/AOB approach from
[`fm_scouter`](https://github.com/dgarfias/fm_scouter):

```powershell
python memory_dump.py --output snapshots/fm24-memory.json
```

If multiple `fm.exe` processes are present, pass `--pid`. Treat the first run
as a validation run because game updates can change signatures or offsets.
Load the resulting JSON in the viewer.

## Data boundary

The viewer and dumper never write to Football Manager. Existing read-only scan
work remains in `fm-project/fm_memory_scan.py`.

## Disclaimer

For personal, single-player use. Not affiliated with Sports Interactive or
SEGA. Football Manager is a trademark of Sports Interactive.
