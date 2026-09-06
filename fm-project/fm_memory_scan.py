from __future__ import annotations

import argparse
from array import array
import json
import shutil
from datetime import datetime
from types import SimpleNamespace
from pathlib import Path

from memory.win_memory import (
    ReadOnlyProcess,
    iter_scan_for_bytes,
    iter_scan_for_value,
    resolve_single_process,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SCAN_DIR = PROJECT_ROOT / "memory" / "scans"
DEFAULT_CONFIG = PROJECT_ROOT / "memory" / "fm24_offsets.json"

PORTSMOUTH_SQUAD_ROWS = {
    "Ethan Thompson-Charnock": [14, 15, 15, 2, 16, 14, 19, 17, 20],
    "Elis Williams": [18, 18, 10, 11, 15, 13, 12, 16, 10],
    "Charlie Hopkinson": [18, 18, 6, 9, 13, 11, 11, 16, 11],
    "Tyler Williams": [18, 16, 18, 7, 14, 12, 12, 13, 12],
    "David Gannon": [19, 16, 14, 10, 16, 15, 11, 15, 14],
    "O'Shaye Asare": [18, 18, 14, 11, 12, 13, 9, 11, 5],
    "Tom Roper": [18, 17, 11, 13, 16, 16, 15, 17, 11],
    "Matthew Adams": [17, 18, 15, 8, 16, 11, 13, 15, 12],
    "Zain Troon": [17, 15, 14, 14, 12, 14, 13, 12, 8],
    "Arjan Beltman": [17, 17, 13, 11, 13, 15, 5, 14, 4],
    "Kady Surey": [18, 18, 13, 12, 12, 10, 9, 15, 6],
    "James Davies": [6, 10, 16, 2, 13, 9, 16, 14, 18],
    "Dan Morris": [18, 18, 13, 8, 15, 15, 12, 16, 11],
    "Neil Hassan": [20, 17, 14, 5, 16, 13, 11, 13, 9],
    "Josh Carter": [18, 16, 16, 5, 13, 11, 11, 13, 14],
    "Calum Austin": [20, 18, 9, 8, 11, 11, 7, 13, 4],
    "Zane Gill": [17, 16, 12, 12, 14, 8, 10, 14, 8],
}


def _parse_address(value: str) -> int:
    return int(value, 16 if value.lower().startswith("0x") else 10)


def _state_path(field: str, state: str | None) -> Path:
    if state:
        return Path(state)
    return DEFAULT_SCAN_DIR / f"{field.lower()}_scan.json"


def _candidate_path(meta_path: Path) -> Path:
    return meta_path.with_suffix(".bin")


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _write_addresses(path: Path, addresses) -> tuple[int, list[int]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample: list[int] = []
    count = 0
    buffer = array("Q")

    with path.open("wb") as handle:
        for address in addresses:
            address = int(address)
            if len(sample) < 20:
                sample.append(address)
            buffer.append(address)
            count += 1
            if len(buffer) >= 100_000:
                buffer.tofile(handle)
                buffer = array("Q")
        if buffer:
            buffer.tofile(handle)

    return count, sample


def _iter_addresses(path: Path):
    chunk_bytes = 8 * 100_000
    with path.open("rb") as handle:
        while True:
            data = handle.read(chunk_bytes)
            if not data:
                break
            values = array("Q")
            values.frombytes(data)
            for value in values:
                yield int(value)


def _intersect_sorted(left, right):
    sentinel = object()
    left_iter = iter(left)
    right_iter = iter(right)
    a = next(left_iter, sentinel)
    b = next(right_iter, sentinel)

    while a is not sentinel and b is not sentinel:
        if a == b:
            yield a
            a = next(left_iter, sentinel)
            b = next(right_iter, sentinel)
        elif a < b:
            a = next(left_iter, sentinel)
        else:
            b = next(right_iter, sentinel)


def _find_ordered_values(
    chunk: bytes,
    values: list[int],
    start: int,
    max_field_gap: int,
) -> list[int] | None:
    positions = [start]
    cursor = start + 1

    for value in values[1:]:
        limit = min(len(chunk), cursor + max_field_gap + 1)
        index = chunk.find(bytes([value]), cursor, limit)
        if index < 0:
            return None
        positions.append(index)
        cursor = index + 1

    return positions


def _find_next_row(
    chunk: bytes,
    row: list[int],
    start: int,
    max_row_gap: int,
    max_field_gap: int,
) -> list[int] | None:
    limit = min(len(chunk), start + max_row_gap + 1)
    cursor = start

    while cursor < limit:
        index = chunk.find(bytes([row[0]]), cursor, limit)
        if index < 0:
            return None
        positions = _find_ordered_values(chunk, row, index, max_field_gap)
        if positions is not None:
            return positions
        cursor = index + 1

    return None


def _open_process(args) -> ReadOnlyProcess:
    pid = resolve_single_process(args.process, args.pid)
    return ReadOnlyProcess(pid)


def scan(args) -> None:
    meta_path = _state_path(args.field, args.state)
    candidate_path = _candidate_path(meta_path)
    with _open_process(args) as process:
        addresses = iter_scan_for_value(
            process,
            args.value,
            value_type=args.type,
            max_region_mb=args.max_region_mb,
        )
        count, sample = _write_addresses(candidate_path, addresses)

    payload = {
        "field": args.field,
        "value_type": args.type,
        "process_name": args.process,
        "pid": args.pid,
        "candidate_file": str(candidate_path),
        "candidate_count": count,
        "last_value": args.value,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "sample": [hex(address) for address in sample],
    }
    _write_json(meta_path, payload)

    print(f"Found {count} candidate addresses for {args.field}={args.value}.")
    print(f"Saved scan state to {meta_path}.")
    print(f"Saved candidates to {candidate_path}.")
    _print_sample(sample, args.limit)


def refine(args) -> None:
    meta_path = _state_path(args.field, args.state)
    payload = _load_json(meta_path)
    value_type = args.type or payload["value_type"]
    candidate_path = Path(payload.get("candidate_file") or _candidate_path(meta_path))
    temp_path = candidate_path.with_suffix(".tmp")

    with _open_process(args) as process:
        current_matches = iter_scan_for_value(
            process,
            args.value,
            value_type=value_type,
            max_region_mb=args.max_region_mb,
        )
        refined = _intersect_sorted(_iter_addresses(candidate_path), current_matches)
        count, sample = _write_addresses(temp_path, refined)

    backup_path = candidate_path.with_suffix(".bak")
    if candidate_path.exists():
        shutil.copy2(candidate_path, backup_path)
    temp_path.replace(candidate_path)

    payload.update(
        {
            "value_type": value_type,
            "candidate_file": str(candidate_path),
            "candidate_count": count,
            "last_value": args.value,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "sample": [hex(address) for address in sample],
        }
    )
    _write_json(meta_path, payload)

    print(f"Refined {args.field} to {count} candidate addresses for value {args.value}.")
    print(f"Updated scan state at {meta_path}.")
    if count == 0:
        print(f"Previous candidates were backed up to {backup_path}.")
    _print_sample(sample, args.limit)


def watch(args) -> None:
    path = _state_path(args.field, args.state)
    payload = _load_json(path)
    value_type = args.type or payload["value_type"]
    candidate_path = Path(payload.get("candidate_file") or _candidate_path(path))

    with _open_process(args) as process:
        rows = []
        for index, address in enumerate(_iter_addresses(candidate_path)):
            if index >= args.limit:
                break
            rows.append((address, process.read_value(address, value_type)))

    print(f"Current values for first {len(rows)} {args.field} candidates:")
    for address, value in rows:
        print(f"{hex(address)} = {value}")


def confirm(args) -> None:
    config_path = Path(args.config)
    if config_path.exists():
        payload = _load_json(config_path)
    else:
        payload = {"process_name": args.process, "fields": {}}

    payload["process_name"] = args.process
    payload.setdefault("fields", {})[args.field] = {
        "address": hex(_parse_address(args.address)),
        "type": args.type,
    }
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(config_path, payload)

    print(f"Saved {args.field} at {args.address} to {config_path}.")


def read_config(args) -> None:
    config_path = Path(args.config)
    payload = _load_json(config_path)
    process_name = args.process or payload.get("process_name", "fm.exe")

    process_args = SimpleNamespace(process=process_name, pid=args.pid)
    with _open_process(process_args) as process:
        row = {}
        for field, spec in payload.get("fields", {}).items():
            row[field] = process.read_value(_parse_address(spec["address"]), spec["type"])

    print(json.dumps(row, indent=2))


def seqscan(args) -> None:
    pattern = bytes(args.values)
    label = args.label or "sequence"
    meta_path = _state_path(label, args.state)
    candidate_path = _candidate_path(meta_path)

    with _open_process(args) as process:
        addresses = iter_scan_for_bytes(
            process,
            pattern,
            max_region_mb=args.max_region_mb,
        )
        count, sample = _write_addresses(candidate_path, addresses)

    payload = {
        "field": label,
        "scan_type": "byte_sequence",
        "process_name": args.process,
        "pid": args.pid,
        "candidate_file": str(candidate_path),
        "candidate_count": count,
        "pattern": list(pattern),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "sample": [hex(address) for address in sample],
    }
    _write_json(meta_path, payload)

    print(f"Found {count} candidate addresses for {label} sequence {list(pattern)}.")
    print(f"Saved scan state to {meta_path}.")
    print(f"Saved candidates to {candidate_path}.")
    _print_sample(sample, args.limit)


def tablescan(args) -> None:
    if args.preset != "portsmouth_squad":
        raise ValueError("Only --preset portsmouth_squad is currently available.")

    rows = list(PORTSMOUTH_SQUAD_ROWS.items())
    hits = []

    with _open_process(args) as process:
        for region in process.iter_readable_regions():
            if region.size > args.max_region_mb * 1024 * 1024:
                continue

            chunk = process.read(region.base, region.size)
            if not chunk:
                continue

            first_name, first_row = rows[0]
            cursor = 0
            while True:
                index = chunk.find(bytes([first_row[0]]), cursor)
                if index < 0:
                    break

                first_positions = _find_ordered_values(
                    chunk,
                    first_row,
                    index,
                    args.max_field_gap,
                )
                if first_positions is None:
                    cursor = index + 1
                    continue

                matched = [(first_name, first_positions)]
                search_from = first_positions[-1] + 1
                for name, row in rows[1:]:
                    positions = _find_next_row(
                        chunk,
                        row,
                        search_from,
                        args.max_row_gap,
                        args.max_field_gap,
                    )
                    if positions is None:
                        break
                    matched.append((name, positions))
                    search_from = positions[-1] + 1

                if len(matched) >= args.min_rows:
                    hit = {
                        "address": region.base + index,
                        "rows_matched": len(matched),
                        "span": matched[-1][1][-1] - matched[0][1][0],
                        "rows": [
                            {
                                "name": name,
                                "offsets": [position - index for position in positions],
                                "address": hex(region.base + positions[0]),
                            }
                            for name, positions in matched
                        ],
                    }
                    hits.append(hit)
                    if len(hits) >= args.limit:
                        break

                cursor = index + 1

            if len(hits) >= args.limit:
                break

    output_path = DEFAULT_SCAN_DIR / "table_scan_hits.json"
    _write_json(
        output_path,
        {
            "preset": args.preset,
            "columns": ["Pac", "Acc", "Jum", "Dri", "Bal", "Wor", "Ant", "Agi", "Cnt"],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "hits": hits,
        },
    )

    print(f"Found {len(hits)} table-pattern hits matching at least {args.min_rows} rows.")
    print(f"Saved hits to {output_path}.")
    for hit in hits[: args.print_limit]:
        print(f"{hex(hit['address'])}: rows={hit['rows_matched']} span={hit['span']}")
        for row in hit["rows"][:5]:
            print(f"  {row['name']}: {row['address']} offsets={row['offsets']}")


def _print_sample(addresses: list[int], limit: int) -> None:
    if not addresses:
        return
    print("Sample candidates:")
    for address in addresses[:limit]:
        print(hex(address))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only FM24 memory scanner for discovering selected-player attribute addresses."
    )
    parser.add_argument("--process", default="fm.exe", help="FM process name. Default: fm.exe")
    parser.add_argument("--pid", type=int, default=None, help="Optional PID if more than one fm.exe is running.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="First scan for a visible attribute value.")
    scan_parser.add_argument("field", help="Field name, for example Acc or Pac.")
    scan_parser.add_argument("value", type=int, help="Visible value in FM.")
    scan_parser.add_argument("--type", choices=["byte", "int"], default="byte")
    scan_parser.add_argument("--state", default=None)
    scan_parser.add_argument("--max-region-mb", type=int, default=256)
    scan_parser.add_argument("--limit", type=int, default=20)
    scan_parser.set_defaults(func=scan)

    refine_parser = subparsers.add_parser("refine", help="Refine candidates after switching player.")
    refine_parser.add_argument("field")
    refine_parser.add_argument("value", type=int)
    refine_parser.add_argument("--type", choices=["byte", "int"], default=None)
    refine_parser.add_argument("--state", default=None)
    refine_parser.add_argument("--max-region-mb", type=int, default=256)
    refine_parser.add_argument("--limit", type=int, default=20)
    refine_parser.set_defaults(func=refine)

    watch_parser = subparsers.add_parser("watch", help="Print current values for candidate addresses.")
    watch_parser.add_argument("field")
    watch_parser.add_argument("--type", choices=["byte", "int"], default=None)
    watch_parser.add_argument("--state", default=None)
    watch_parser.add_argument("--limit", type=int, default=20)
    watch_parser.set_defaults(func=watch)

    confirm_parser = subparsers.add_parser("confirm", help="Save a confirmed address to the offset config.")
    confirm_parser.add_argument("field")
    confirm_parser.add_argument("address")
    confirm_parser.add_argument("--type", choices=["byte", "int"], default="byte")
    confirm_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    confirm_parser.set_defaults(func=confirm)

    read_parser = subparsers.add_parser("read", help="Read all confirmed fields from the offset config.")
    read_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    read_parser.set_defaults(func=read_config)

    seqscan_parser = subparsers.add_parser("seqscan", help="Scan for a contiguous byte sequence.")
    seqscan_parser.add_argument("values", type=int, nargs="+", help="Byte values, for example: 16 14 14 12")
    seqscan_parser.add_argument("--label", default=None)
    seqscan_parser.add_argument("--state", default=None)
    seqscan_parser.add_argument("--max-region-mb", type=int, default=256)
    seqscan_parser.add_argument("--limit", type=int, default=20)
    seqscan_parser.set_defaults(func=seqscan)

    tablescan_parser = subparsers.add_parser("tablescan", help="Search for repeated squad-table attribute rows.")
    tablescan_parser.add_argument("--preset", default="portsmouth_squad")
    tablescan_parser.add_argument("--min-rows", type=int, default=4)
    tablescan_parser.add_argument("--max-field-gap", type=int, default=16)
    tablescan_parser.add_argument("--max-row-gap", type=int, default=512)
    tablescan_parser.add_argument("--max-region-mb", type=int, default=256)
    tablescan_parser.add_argument("--limit", type=int, default=20)
    tablescan_parser.add_argument("--print-limit", type=int, default=5)
    tablescan_parser.set_defaults(func=tablescan)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
