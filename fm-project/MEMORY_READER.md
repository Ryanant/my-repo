# FM24 Memory Reader

This is a read-only scanner for discovering FM24 selected-player attribute
addresses. It does not write to the FM process.

## First target

Start with one visible attribute on the currently selected player, for example
`Acceleration`.

From your screenshot:

- Process: `fm.exe`
- Player: Ethan Thompson-Charnock
- Acceleration: `15`
- Pace: `14`

## Workflow

Open FM24 on a player profile, then run commands from `fm-project`.

First scan:

```powershell
python fm_memory_scan.py scan Acc 15
```

This writes a small metadata file plus a binary candidate list in
`memory/scans`. A first one-byte scan can still produce millions of candidates;
the refine steps are what make it useful.

Switch to another player in FM24 and note their visible Acceleration. Refine:

```powershell
python fm_memory_scan.py refine Acc 12
```

Switch to another player again and refine again:

```powershell
python fm_memory_scan.py refine Acc 17
```

Repeat until there are only a few candidates. Then watch them while switching
players:

```powershell
python fm_memory_scan.py watch Acc
```

When one address always equals the selected player's visible Acceleration, save
it:

```powershell
python fm_memory_scan.py confirm Acc 0x123456789ABC
```

Repeat for `Pac`, `Agi`, `Bal`, `Jum`, and any other attributes you want.

Read confirmed values:

```powershell
python fm_memory_scan.py read
```

## Notes

- Use `byte` for normal FM attributes first, because they are usually 1-20.
- If a scan finds nothing useful, retry with `--type int`.
- If Windows blocks process access, run PowerShell as administrator.
- If more than one FM process is running, pass the PID:

```powershell
python fm_memory_scan.py --pid 19108 scan Acc 15
```
