"""Read-only FM24 (24.4.2) player-table dumper for Windows.

The signatures and offsets follow dgarfias/fm_scouter's FM24 research. They
must be revalidated after an FM24 executable update. This module requests only
PROCESS_VM_READ and never writes to the game process.
"""
from __future__ import annotations
import argparse, ctypes, ctypes.wintypes as wintypes, hashlib, json, re, struct
from datetime import date, datetime, timedelta
from collections import Counter
from pathlib import Path

PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
TH32CS_SNAPPROCESS, INVALID_HANDLE_VALUE = 0x2, ctypes.c_void_p(-1).value
MEM_COMMIT, PAGE_GUARD, PAGE_NOACCESS = 0x1000, 0x100, 0x01
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}
KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("heap", ctypes.POINTER(wintypes.ULONG)), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD), ("exe", ctypes.c_wchar * 260)]

class MBI(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("allocation", ctypes.c_void_p), ("allocation_protect", wintypes.DWORD),
                ("size", ctypes.c_size_t), ("state", wintypes.DWORD), ("protect", wintypes.DWORD), ("type", wintypes.DWORD)]

KERNEL.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
KERNEL.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
KERNEL.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
KERNEL.Process32FirstW.restype = wintypes.BOOL
KERNEL.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
KERNEL.Process32NextW.restype = wintypes.BOOL
KERNEL.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
KERNEL.OpenProcess.restype = wintypes.HANDLE
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL.CloseHandle.restype = wintypes.BOOL
KERNEL.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
KERNEL.VirtualQueryEx.restype = ctypes.c_size_t
KERNEL.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
KERNEL.ReadProcessMemory.restype = wintypes.BOOL

def fm_pids():
    snap = KERNEL.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE: return []
    try:
        e = PROCESSENTRY32W(); e.dwSize = ctypes.sizeof(e); result = []
        if not KERNEL.Process32FirstW(snap, ctypes.byref(e)): return result
        while True:
            if e.exe.lower() == "fm.exe": result.append(int(e.pid))
            if not KERNEL.Process32NextW(snap, ctypes.byref(e)): break
        return result
    finally: KERNEL.CloseHandle(snap)

class ReadOnlyMemory:
    def __init__(self, pid):
        self.handle = KERNEL.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not self.handle: raise PermissionError("Could not open FM24 read-only; try an elevated terminal.")
    def close(self):
        if self.handle: KERNEL.CloseHandle(self.handle); self.handle = None
    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def read(self, address, size):
        buf, got = ctypes.create_string_buffer(size), ctypes.c_size_t()
        ok = KERNEL.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got))
        return buf.raw if ok and got.value == size else None
    def u16(self, address):
        data = self.read(address, 2); return struct.unpack("<H", data)[0] if data else 0
    def u32(self, address):
        data = self.read(address, 4); return struct.unpack("<I", data)[0] if data else 0
    def u64(self, address):
        data = self.read(address, 8); return struct.unpack("<Q", data)[0] if data else 0
    def regions(self):
        address, mbi_size = 0, ctypes.sizeof(MBI)
        while address < 0x7FFFFFFFFFFF:
            mbi = MBI()
            if not KERNEL.VirtualQueryEx(self.handle, ctypes.c_void_p(address), ctypes.byref(mbi), mbi_size):
                address += 0x10000; continue
            base, size, protect = int(mbi.base or 0), int(mbi.size or 0), int(mbi.protect or 0)
            if int(mbi.state) == MEM_COMMIT and not protect & PAGE_GUARD and not protect & PAGE_NOACCESS and protect & 0xFF in READABLE and size:
                yield base, size
            address = base + max(size, 0x1000)

def _aob(text):
    parts = text.split()
    return (bytes(0 if x in {"?", "??"} else int(x, 16) for x in parts),
            bytes(0 if x in {"?", "??"} else 255 for x in parts))

def _scan(process, pattern, mask):
    fixed = [(i, value) for i, value in enumerate(pattern) if mask[i]]
    if not fixed:
        return
    anchor_start = fixed[0][0]
    anchor = bytes(value for _, value in fixed[:3]) if all(i == anchor_start + n for n, (i, _) in enumerate(fixed[:3])) else bytes([fixed[0][1]])
    for base, size in process.regions():
        if size > 256 * 1024 * 1024: continue
        data = process.read(base, size)
        if not data: continue
        search = 0
        while True:
            anchor_at = data.find(anchor, search)
            if anchor_at < 0: break
            candidate = anchor_at - anchor_start
            if candidate >= 0 and candidate + len(pattern) <= len(data) and all(not mask[j] or data[candidate + j] == pattern[j] for j in range(len(pattern))):
                yield base + candidate
            search = anchor_at + 1

ATTRS = {
    # Technical
    "crossing": 0x00, "dribbling": 0x01, "finishing": 0x02, "heading": 0x03,
    "long_shots": 0x04, "marking": 0x05, "passing": 0x07, "penalty_taking": 0x08,
    "tackling": 0x09, "first_touch": 0x16, "technique": 0x17, "corners": 0x1B,
    "long_throws": 0x1E, "free_kick_taking": 0x23,
    # Mental
    "off_the_ball": 0x06, "vision": 0x0A, "anticipation": 0x11, "decisions": 0x12,
    "positioning": 0x14, "flair": 0x1A, "teamwork": 0x1C, "work_rate": 0x1D,
    "leadership": 0x28, "bravery": 0x2B, "aggression": 0x2D,
    "determination": 0x33, "composure": 0x34, "concentration": 0x35,
    # Physical
    "acceleration": 0x22, "strength": 0x24, "stamina": 0x25, "pace": 0x26,
    "jumping_reach": 0x27, "balance": 0x2A, "agility": 0x2E, "natural_fitness": 0x32,
    # Goalkeeping
    "handling": 0x0B, "aerial_reach": 0x0C, "command_of_area": 0x0D,
    "communication": 0x0E, "kicking": 0x0F, "throwing": 0x10,
    "one_on_ones": 0x13, "reflexes": 0x15, "eccentricity": 0x1F,
    "rushing_out": 0x20, "punching": 0x21,
    # Other hidden attributes stored in the same block.
    "left_foot": 0x18, "right_foot": 0x19, "dirtiness": 0x29,
    "consistency": 0x2C, "important_matches": 0x2F, "injury_proneness": 0x30,
    "versatility": 0x31,
}
PERSONALITY_FIELDS = ("Adaptability", "Ambition", "Loyalty", "Pressure", "Professionalism", "Sportsmanship", "Temperament", "Controversy")
POSITIONS = ["GK","SW","DL","DC","DR","DM","ML","MC","MR","AML","AMC","AMR","ST","WBL","WBR"]

def _text(process, entry):
    if not entry: return ""
    data = process.read(entry + 4, 96)
    value = data.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip() if data else ""
    if value and value.isprintable(): return value
    head = process.u64(entry)
    data = process.read(head + 4, 96) if head else None
    return data.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip() if data else ""


def _club_name(process, person):
    """Resolve Person -> full contract -> team -> club -> display name."""
    contract = process.u64(person + 0xC8)
    team = process.u64(contract + 0x10) if contract else 0
    club = process.u64(team + 0x30) if team else 0
    name_entry = process.u64(club + 0xC0) if club else 0
    name = _text(process, name_entry)
    return name or ("Free Transfer" if not club else "Unknown")


def _person_name(process, person):
    first = _text(process, process.u64(person + 0x58))
    surname = _text(process, process.u64(person + 0x60))
    common = _text(process, process.u64(person + 0x68))
    # FM's common-name field is what the game displays (nicknames and
    # preferred names). Use the full first/surname pair only as a fallback.
    return common or " ".join(part for part in (first, surname) if part) or "Unknown"


def _person_dob(process, person):
    """Decode FM's packed DOB at Person+0x40 (day-of-year, year)."""
    packed = process.u64(person + 0x40)
    day_of_year, year = packed >> 32 & 0xFFFF, packed >> 48 & 0xFFFF
    if not (1900 <= year <= 2100 and 1 <= day_of_year <= 366):
        return None
    try:
        return (date(year, 1, 1) + timedelta(days=day_of_year - 1)).isoformat()
    except ValueError:
        return None


def _packed_date(value):
    """Decode the date layout used by Person+0x40, if *value* matches it."""
    day_of_year, year = value >> 32 & 0xFFFF, value >> 48 & 0xFFFF
    if not (1900 <= year <= 2100 and 1 <= day_of_year <= 366):
        return None
    try:
        return (date(year, 1, 1) + timedelta(days=day_of_year - 1)).isoformat()
    except ValueError:
        return None


def _scheduled_game_date(value):
    try:
        current = date.fromisoformat(value or "")
    except (TypeError, ValueError):
        return False
    return current.day == 1 and current.month in {1, 4, 7, 10}


def _prune_unscheduled_archives(directory: Path, game_date: str | None):
    """After a quarterly capture, discard interim archive snapshots."""
    if not _scheduled_game_date(game_date):
        return
    for archive in directory.glob("fm24-memory-*.json"):
        try:
            payload = json.loads(archive.read_text(encoding="utf-8"))
            archived_date = payload.get("Game Date") if isinstance(payload, dict) else None
        except (OSError, ValueError, json.JSONDecodeError):
            archived_date = None
        if not _scheduled_game_date(archived_date):
            archive.unlink(missing_ok=True)


def debug_packed_dates(process):
    """Report repeated packed-date values to help identify FM's global date."""
    matches = Counter()
    locations = {}
    for base, size in process.regions():
        if size > 256 * 1024 * 1024:
            continue
        data = process.read(base, size)
        if not data:
            continue
        for offset in range(0, len(data) - 7, 8):
            value = struct.unpack_from("<Q", data, offset)[0]
            decoded = _packed_date(value)
            if decoded:
                matches[decoded] += 1
                locations.setdefault(decoded, base + offset)
    for decoded, count in matches.most_common(30):
        print(f"{decoded} count={count} first={locations[decoded]:#018x}")


def debug_date_strings(process, text="27/4/2024"):
    """Find the visible FM date in common ANSI/UTF-16 string encodings."""
    needles = {
        "ascii": text.encode("ascii"),
        "utf16": text.encode("utf-16-le"),
        "ascii_padded": text.replace("/", " / ").encode("ascii"),
        "utf16_padded": text.replace("/", " / ").encode("utf-16-le"),
    }
    found = 0
    for base, size in process.regions():
        if size > 256 * 1024 * 1024:
            continue
        data = process.read(base, size)
        if not data:
            continue
        for label, needle in needles.items():
            cursor = 0
            while True:
                hit = data.find(needle, cursor)
                if hit < 0:
                    break
                address = base + hit
                context = data[max(0, hit - 32):min(len(data), hit + len(needle) + 64)]
                print(f"{label} {address:#018x}: {context[:].hex(' ')}")
                found += 1
                cursor = hit + 1
                if found >= 100:
                    return
    print(f"matches={found}")


def _live_game_date(process):
    """Read FM's live status text, which contains ``Current date: d/m/yyyy``."""
    candidates = Counter()
    marker = b"Current date:"
    pattern = re.compile(rb"Current date:\s*(\d{1,2})/(\d{1,2})/(\d{4})")
    for base, size in process.regions():
        if size > 256 * 1024 * 1024:
            continue
        data = process.read(base, size)
        if not data or marker not in data:
            continue
        for match in pattern.finditer(data):
            try:
                value = date(int(match.group(3)), int(match.group(2)), int(match.group(1))).isoformat()
            except ValueError:
                continue
            candidates[value] += 1
    if not candidates:
        return None
    return candidates.most_common(1)[0][0]


def debug_address(process, address):
    """Dump a candidate date string and locate pointers to nearby bytes."""
    print(f"candidate={address:#018x}")
    data = process.read(address - 0x100, 0x300)
    if data:
        print(data.decode("utf-8", errors="backslashreplace"))
        print(data.hex(" "))
    targets = {address + offset for offset in range(-0x40, 0x41)}
    references = 0
    for base, size in process.regions():
        if size > 256 * 1024 * 1024:
            continue
        data = process.read(base, size)
        if not data:
            continue
        for offset in range(0, len(data) - 7, 8):
            value = struct.unpack_from("<Q", data, offset)[0]
            if value in targets:
                print(f"reference {base + offset:#018x} -> {value:#018x}")
                references += 1
                if references >= 100:
                    return
    print(f"references={references}")



def dump(pid: int, output: Path, debug_id: int | None = None, game_date: str | None = None, debug_db: bool = False):
    with ReadOnlyMemory(pid) as process:
        table = None
        # Native Windows/FM24 24.4.2 signature from the matching CE table:
        #   lea rdi,[rcx+disp32]
        #   mov r9,[rip+disp32]   <-- dbtRoot global
        #   lea rcx,[rip+disp32]
        # The table stores the address of the global, not its current value.
        for match in _scan(process, *_aob(
            "48 8D B9 ?? ?? ?? ?? 4C 8B 0D ?? ?? ?? ?? 48 8D 0D ?? ?? ?? ??"
        )):
            raw = process.read(match + 0x0A, 4)
            if not raw: continue
            dbt = match + 0x0A + 4 + struct.unpack("<i", raw)[0]
            person_db, table_ptr = process.u64(dbt + 0x68), 0
            if person_db: table_ptr = process.u64(person_db + 0x80)
            if not table_ptr: continue
            if debug_db:
                print(f"dbt={dbt:#018x} person_db={person_db:#018x} table_ptr={table_ptr:#018x}")
                for offset in range(0, 0x401, 8):
                    print(f"dbt+{offset:#05x}: {process.u64(dbt + offset):#018x}")
                print("person_db:")
                for offset in range(0, 0x401, 8):
                    print(f"person_db+{offset:#05x}: {process.u64(person_db + offset):#018x}")
            start, end = process.u64(table_ptr), process.u64(table_ptr + 8)
            count = (end - start) // 8 if end > start else 0
            if 1000 < count < 500000: table = (start, end); break
        if not table: raise RuntimeError("Could not resolve FM24 person table; check build/signatures.")
        game_date = game_date or _live_game_date(process)
        if game_date:
            print(f"Detected FM24 in-game date: {game_date}")
        else:
            print("Warning: FM24 in-game date was not found; Age will be blank for this capture.")
        start, end, rows, pointer_count, typed_count, type_counts = *table, [], 0, 0, Counter()
        for address in range(start, end, 8):
            person = process.u64(address)
            if not person: continue
            pointer_count += 1
            vtable, type_info = process.u64(person), 0
            if vtable: type_info = process.u64(vtable - 8)
            if not type_info: continue
            type_offset = process.u32(type_info + 4); type_counts[type_offset] += 1
            if type_offset != 0x278: continue
            typed_count += 1
            if debug_id is not None and process.u32(person + 0x0C) == debug_id:
                print(f"DEBUG person {hex(person)} id={debug_id}")
                contract = process.u64(person + 0xC8)
                team = process.u64(contract + 0x10) if contract else 0
                club = process.u64(team + 0x30) if team else 0
                print(f"DEBUG chain contract={contract:#018x} team={team:#018x} club={club:#018x}")
                for label, target in (("contract", contract), ("team", team), ("club", club)):
                    if target:
                        print(f"DEBUG {label} object:")
                        print("    " + " ".join(f"{process.u64(target + n):016x}" for n in range(0, 0x108, 8)))
                for offset in range(0, 0x181, 8):
                    print(f"  +{offset:#05x}: {process.u64(person + offset):#018x}")
                print("DEBUG preceding-object qwords:")
                for offset in range(0, 0x301, 8):
                    print(f"  -0x278+{offset:#05x}: {process.u64(person - 0x278 + offset):#018x}")
                print("DEBUG referenced objects:")
                seen = set()
                for offset in range(0, 0x181, 8):
                    target = process.u64(person + offset)
                    if not target or target in seen or target < 0x100000:
                        continue
                    seen.add(target)
                    vtable = process.u64(target)
                    type_info = process.u64(vtable - 8) if vtable else 0
                    type_offset = process.u32(type_info + 4) if type_info else 0
                    print(f"  person+{offset:#05x} -> {target:#018x} type_offset={type_offset:#x}")
                    print("    " + " ".join(f"{process.u64(target + n):016x}" for n in range(0, 0x58, 8)))
                needle = struct.pack("<Q", person)
                reference_count = 0
                print("DEBUG reverse references:")
                for base, size in process.regions():
                    if size > 256 * 1024 * 1024:
                        continue
                    data = process.read(base, size)
                    if not data:
                        continue
                    cursor = 0
                    while True:
                        hit = data.find(needle, cursor)
                        if hit < 0:
                            break
                        address = base + hit
                        if address != person:
                            print(f"  {address:#018x} (offset from person object: {address - person:+#x})")
                            context = [process.u64(address + n) for n in range(-0x20, 0x28, 8)]
                            print("    context: " + " ".join(f"{value:016x}" for value in context))
                            reference_count += 1
                            if reference_count >= 40:
                                break
                        cursor = hit + 1
                    if reference_count >= 40:
                        break
                print(f"  total shown: {reference_count}")
            plao, attrs = person - 0x278, process.read(person - 0x278 + 0x217, 0x36)
            if not attrs: continue
            positions = process.read(plao + 0x208, 15) or b""
            dob = _person_dob(process, person)
            row = {"ID": process.u32(person + 0x0C), "Name": _person_name(process, person), "DoB": dob,
                   "Club": _club_name(process, person),
                   "Current Ability": process.u16(plao + 0x200), "Potential Ability": process.u16(plao + 0x202),
                   "Positions": [POSITIONS[i] for i, value in enumerate(positions) if value >= 15], "Source": "FM24 memory 24.4.2"}
            row.update({key: attrs[pos] // 5 for key, pos in ATTRS.items()})
            personality = process.read(person + 0x78, len(PERSONALITY_FIELDS)) or b""
            row.update({name: personality[index] for index, name in enumerate(PERSONALITY_FIELDS) if index < len(personality) and personality[index] > 0})
            if game_date and dob:
                try:
                    game_day = date.fromisoformat(game_date)
                    birth_day = date.fromisoformat(dob)
                    row["Age"] = round((game_day - birth_day).days / 365.25, 4)
                except ValueError:
                    pass
            rows.append(row)
    if not rows:
        print(f"No validated players found (non-null table pointers: {pointer_count}; player-typed: {typed_count})")
        if not typed_count:
            print("Top type offsets:", ", ".join(f"{hex(value)}={count}" for value, count in type_counts.most_common(10)) or "none")
        raise RuntimeError("FM24 native Windows memory layout/signature is not validated for this build.")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"players": rows, "Game Date": game_date}, indent=2)
    output.write_text(payload, encoding="utf-8")
    # Preserve each capture for the development tracker. The explicitly named
    # output remains the convenient latest snapshot for scripts and the UI.
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    archived = sorted(output.parent.glob(f"{output.stem}-*{output.suffix}"), key=lambda path: path.stat().st_mtime_ns)
    already_archived = False
    if archived:
        already_archived = hashlib.sha256(archived[-1].read_bytes()).hexdigest() == digest
    if not already_archived:
        archive = output.with_name(f"{output.stem}-{datetime.now():%Y%m%d-%H%M%S}{output.suffix}")
        archive.write_text(payload, encoding="utf-8")
    _prune_unscheduled_archives(output.parent, game_date)
    print(f"Wrote {len(rows)} players to {output} (non-null table pointers: {pointer_count}; player-typed: {typed_count})")
    if not typed_count:
        print("Top type offsets:", ", ".join(f"{hex(value)}={count}" for value, count in type_counts.most_common(10)) or "none")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only FM24 memory dump")
    parser.add_argument("--pid", type=int); parser.add_argument("--list", action="store_true", help="list detected fm.exe processes and exit")
    parser.add_argument("--output", type=Path, default=Path("snapshots/fm24-memory.json"))
    parser.add_argument("--game-date", help="in-game date for this capture, e.g. 2024-04-01")
    parser.add_argument("--debug-id", type=int, help="print pointer fields for one player UID")
    parser.add_argument("--debug-packed-dates", action="store_true", help="scan live memory for packed FM dates and exit")
    parser.add_argument("--debug-date-strings", action="store_true", help="find the visible in-game date in process memory and exit")
    parser.add_argument("--debug-address", type=lambda value: int(value, 0), help="inspect a candidate memory address and its references")
    parser.add_argument("--debug-db", action="store_true", help="print database root fields and exit after resolving it")
    args = parser.parse_args(); pids = fm_pids() if args.pid is None else [args.pid]
    if args.list:
        print("Detected fm.exe PIDs:", pids or "none")
        raise SystemExit(0)
    if len(pids) != 1: raise SystemExit(f"Expected one FM process; found {pids}. Pass --pid.")
    if args.debug_packed_dates:
        with ReadOnlyMemory(pids[0]) as process:
            debug_packed_dates(process)
        raise SystemExit(0)
    if args.debug_date_strings:
        with ReadOnlyMemory(pids[0]) as process:
            debug_date_strings(process)
        raise SystemExit(0)
    if args.debug_address is not None:
        with ReadOnlyMemory(pids[0]) as process:
            debug_address(process, args.debug_address)
        raise SystemExit(0)
    # The normal path must never infer the date from an export: exports are
    # now optional historical data and may be stale.  Automatic date reading
    # will be supplied by the live FM memory reader; --game-date remains only
    # as a backwards-compatible diagnostic override.
    game_date = args.game_date
    dump(pids[0], args.output, args.debug_id, game_date, args.debug_db)
