from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import struct
from dataclasses import dataclass
from typing import Iterable


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01

READABLE_PROTECTIONS = {
    0x02,  # PAGE_READONLY
    0x04,  # PAGE_READWRITE
    0x08,  # PAGE_WRITECOPY
    0x20,  # PAGE_EXECUTE_READ
    0x40,  # PAGE_EXECUTE_READWRITE
    0x80,  # PAGE_EXECUTE_WRITECOPY
}


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL


@dataclass(frozen=True)
class MemoryRegion:
    base: int
    size: int
    protect: int


def _last_error_message() -> str:
    return ctypes.FormatError(ctypes.get_last_error()).strip()


def find_processes_by_name(process_name: str) -> list[tuple[int, str]]:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise OSError(f"Could not create process snapshot: {_last_error_message()}")

    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        processes: list[tuple[int, str]] = []

        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return processes

        while True:
            exe = entry.szExeFile
            if exe.lower() == process_name.lower():
                processes.append((int(entry.th32ProcessID), exe))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break

        return processes
    finally:
        kernel32.CloseHandle(snapshot)


class ReadOnlyProcess:
    def __init__(self, pid: int):
        self.pid = int(pid)
        self.handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
            False,
            self.pid,
        )
        if not self.handle:
            raise PermissionError(
                f"Could not open process {self.pid} read-only: {_last_error_message()}. "
                "Try running PowerShell as administrator."
            )

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "ReadOnlyProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def iter_readable_regions(self) -> Iterable[MemoryRegion]:
        address = 0
        mbi = MEMORY_BASIC_INFORMATION()
        mbi_size = ctypes.sizeof(mbi)

        while address < 0x7FFFFFFFFFFF:
            result = kernel32.VirtualQueryEx(
                self.handle,
                ctypes.c_void_p(address),
                ctypes.byref(mbi),
                mbi_size,
            )
            if not result:
                address += 0x10000
                continue

            base = int(mbi.BaseAddress or 0)
            size = int(mbi.RegionSize or 0)
            protect = int(mbi.Protect or 0)
            is_readable = (
                int(mbi.State) == MEM_COMMIT
                and protect & PAGE_GUARD == 0
                and protect & PAGE_NOACCESS == 0
                and (protect & 0xFF) in READABLE_PROTECTIONS
            )
            if is_readable and size > 0:
                yield MemoryRegion(base=base, size=size, protect=protect)

            next_address = base + max(size, 0x1000)
            if next_address <= address:
                break
            address = next_address

    def read(self, address: int, size: int) -> bytes | None:
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(int(address)),
            buffer,
            size,
            ctypes.byref(bytes_read),
        )
        if not ok or bytes_read.value != size:
            return None
        return buffer.raw

    def read_value(self, address: int, value_type: str):
        data = self.read(address, value_size(value_type))
        if data is None:
            return None
        return unpack_value(data, value_type)


def value_size(value_type: str) -> int:
    if value_type == "byte":
        return 1
    if value_type == "int":
        return 4
    raise ValueError(f"Unsupported value type: {value_type}")


def pack_value(value: int, value_type: str) -> bytes:
    if value_type == "byte":
        if not 0 <= int(value) <= 255:
            raise ValueError("Byte values must be between 0 and 255")
        return struct.pack("<B", int(value))
    if value_type == "int":
        return struct.pack("<i", int(value))
    raise ValueError(f"Unsupported value type: {value_type}")


def unpack_value(data: bytes, value_type: str) -> int:
    if value_type == "byte":
        return struct.unpack("<B", data)[0]
    if value_type == "int":
        return struct.unpack("<i", data)[0]
    raise ValueError(f"Unsupported value type: {value_type}")


def scan_for_value(
    process: ReadOnlyProcess,
    value: int,
    value_type: str = "byte",
    max_region_mb: int = 256,
) -> list[int]:
    return list(iter_scan_for_value(process, value, value_type, max_region_mb))


def iter_scan_for_value(
    process: ReadOnlyProcess,
    value: int,
    value_type: str = "byte",
    max_region_mb: int = 256,
) -> Iterable[int]:
    pattern = pack_value(value, value_type)
    max_region_size = max_region_mb * 1024 * 1024

    for region in process.iter_readable_regions():
        if region.size > max_region_size:
            continue
        chunk = process.read(region.base, region.size)
        if not chunk:
            continue

        start = 0
        while True:
            index = chunk.find(pattern, start)
            if index < 0:
                break
            yield region.base + index
            start = index + 1


def iter_scan_for_bytes(
    process: ReadOnlyProcess,
    pattern: bytes,
    max_region_mb: int = 256,
) -> Iterable[int]:
    if not pattern:
        raise ValueError("Pattern must not be empty")

    max_region_size = max_region_mb * 1024 * 1024

    for region in process.iter_readable_regions():
        if region.size > max_region_size:
            continue
        chunk = process.read(region.base, region.size)
        if not chunk:
            continue

        start = 0
        while True:
            index = chunk.find(pattern, start)
            if index < 0:
                break
            yield region.base + index
            start = index + 1


def resolve_single_process(process_name: str, pid: int | None = None) -> int:
    if pid is not None:
        return int(pid)

    matches = find_processes_by_name(process_name)
    if not matches:
        raise LookupError(f"No running process named {process_name!r} was found.")
    if len(matches) > 1:
        pids = ", ".join(str(match_pid) for match_pid, _ in matches)
        raise LookupError(f"Multiple {process_name!r} processes found. Re-run with --pid. PIDs: {pids}")
    return matches[0][0]
