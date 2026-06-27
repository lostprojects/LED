#!/usr/bin/env python3
"""
harness.py - Unicorn emulation harness for CLTDevice.dll (32-bit PE).

Goal: run the DLL's OWN config serializer offline (no Windows, no network) to
capture the exact bytes it would transmit. We:
  1. Map CLTDevice.dll at its image base (0x10000000) - no relocation needed.
  2. Set up stack, a bump heap, and an FS/TEB segment (the serializer uses SEH).
  3. Trap every imported WinAPI/CLTNic/zlib call via per-import sentinel addrs in
     the IAT and dispatch to Python shims (heap, file I/O serving the .rcvp,
     Nic_Write capture, Nic_Read ack, etc.).
  4. Call CLTReceiverRcvParamInitFromFile(path) to load a .rcvp into the singleton.
  5. Call CLTReceiverRcvParamSaveToDevice(...) and capture each Nic_Write buffer
     = the ground-truth wire frames for every config section, in send order.

This is iterative: run, see what traps, add a shim, repeat.
"""
import sys, struct
from collections import deque
import pefile
from unicorn import *
from unicorn.x86_const import *

DLL = sys.argv[1] if len(sys.argv) > 1 else "/home/muse/Desktop/LED/re/dll/CLTDevice.dll"
RCVP = sys.argv[2] if len(sys.argv) > 2 else \
    "/home/muse/Desktop/LED/re/config_files/General Parameters(Fullcolor)/26- full-color thirty-two scan.rcvp"

IMAGE_BASE = 0x10000000

# memory regions
STACK_BASE = 0x20000000
STACK_SIZE = 0x10000000          # 256 MB (CRT lazy locale init is stack-hungry)
STACK_TOP  = STACK_BASE + STACK_SIZE - 0x10000

HEAP_BASE  = 0x40000000
HEAP_SIZE  = 0x10000000          # 256 MB bump arena
heap_ptr   = HEAP_BASE

TEB_BASE   = 0x00180000          # TEB/PEB scratch
GDT_BASE   = 0x00170000

HOOK_BASE  = 0x70000000          # one sentinel addr per imported function
HOOK_SIZE  = 0x00010000

EXPORTS = {}   # name -> VA  (filled from PE)

# -------------------------------------------------------------- import shims
# argcount table for stdcall cleanup. cdecl funcs listed separately (caller cleans).
ARGC = {
    # KERNEL32 - heap
    "GetProcessHeap":0, "HeapAlloc":3, "HeapFree":3, "HeapReAlloc":4, "HeapSize":3,
    # KERNEL32 - file
    "CreateFileW":7, "CreateFileA":7, "ReadFile":5, "WriteFile":5, "SetFilePointerEx":5,
    "SetFilePointer":4, "CloseHandle":1, "GetFileType":1, "GetFileSizeEx":2, "GetFileSize":2,
    "FlushFileBuffers":1, "GetFileAttributesW":1, "GetFileAttributesA":1,
    "DeviceIoControl":8, "CreateFileMappingW":6, "MapViewOfFile":5,
    # KERNEL32 - misc / CRT support
    "GetLastError":0, "SetLastError":1, "GetCurrentThreadId":0, "GetCurrentProcessId":0,
    "GetCurrentProcess":0, "GetCurrentThread":0, "Sleep":1, "GetTickCount":0,
    "QueryPerformanceCounter":1, "QueryPerformanceFrequency":1, "GetSystemTimeAsFileTime":1,
    "EnterCriticalSection":1, "LeaveCriticalSection":1, "DeleteCriticalSection":1,
    "InitializeCriticalSection":1, "InitializeCriticalSectionAndSpinCount":2,
    "InitializeCriticalSectionEx":3,
    "TlsAlloc":0, "TlsFree":1, "TlsGetValue":1, "TlsSetValue":2,
    "MultiByteToWideChar":6, "WideCharToMultiByte":8, "GetStringTypeW":5,
    "GetModuleHandleW":1, "GetModuleHandleA":1, "GetModuleHandleExW":3,
    "GetProcAddress":2, "LoadLibraryW":1, "LoadLibraryExW":3, "FreeLibrary":1,
    "GetModuleFileNameW":3, "GetModuleFileNameA":3,
    "VirtualAlloc":4, "VirtualFree":3, "VirtualProtect":4,
    "EncodePointer":1, "DecodePointer":1, "RaiseException":4, "RtlUnwind":4,
    "OutputDebugStringW":1, "OutputDebugStringA":1, "IsDebuggerPresent":0,
    "IsProcessorFeaturePresent":1, "InitializeSListHead":1,
    "SetUnhandledExceptionFilter":1, "UnhandledExceptionFilter":1,
    "GetCPInfo":2, "GetACP":0, "GetOEMCP":0, "IsValidCodePage":1,
    "GetStdHandle":1, "WriteConsoleW":5, "GetConsoleMode":2, "GetConsoleCP":0,
    "GetCommandLineA":0, "GetCommandLineW":0, "GetEnvironmentStringsW":0,
    "FreeEnvironmentStringsW":1, "GetModuleHandleExW":3, "AreFileApisANSI":0,
    "LCMapStringW":6, "CompareStringW":6, "GetLocaleInfoW":4, "GetUserDefaultLCID":0,
    "IsValidLocale":2, "EnumSystemLocalesW":2, "GetTimeZoneInformation":1,
    "SetStdHandle":2, "SetEndOfFile":1, "GetStartupInfoW":1, "WideCharToMultiByte":8,
    "SetEnvironmentVariableA":2, "GetVersionExW":1, "InterlockedFlushSList":1,
    "QueryDepthSList":1, "SetThreadAffinityMask":2, "GetProcessAffinityMask":3,
    "GetVersionExW":1, "GetVersionExA":1, "GetVersion":0,
    "CreateThread":6, "CreateEventW":4, "SetEvent":1, "WaitForSingleObject":2,
    "CloseHandle":1, "GetOverlappedResult":4, "ResetEvent":1,
    # ole32 / shell / iphlpapi / ws2
    "CoCreateGuid":1, "SHGetSpecialFolderLocation":3, "SHGetPathFromIDListW":2,
    "SHCreateDirectoryExW":3, "GetAdaptersInfo":2,
    "WSAStartup":2, "WSACleanup":0, "socket":3, "closesocket":1, "htons":1, "htonl":1,
    "ntohs":1, "ntohl":1, "bind":3, "setsockopt":5, "ioctlsocket":3,
    "gethostname":2, "gethostbyname":1,
    # CLTNic (decorated @N)
    "_Nic_Write@8":2, "_Nic_Read@20":5, "_Nic_SetBlockFlags@4":1, "_Nic_ClearReadCache@0":0,
    "_Nic_IsSenderRunning@0":0, "_Nic_SetBrightness@24":6, "_Nic_GetNetAdapterCount@8":2,
    "_Nic_SetScreenShowOnOff@4":1,
}
CDECL = {"uncompress","compress","inflate","inflateEnd","inflateInit_","deflate",
         "deflateEnd","deflateInit_","LZ4_decompress_safe","LZ4_compress_fast"}

# fake file: serves the .rcvp
class FakeFile:
    def __init__(self, data): self.data=data; self.pos=0
rcvp_bytes = open(RCVP,"rb").read()
FILES = {}        # handle -> FakeFile
NEXT_HANDLE = 0x1000
nic_writes = []   # captured (buf bytes)
WRITES = []       # captured WriteFile payloads (e.g. data_emu.txt generator output)
trace_imports = True
DEBUG_TRACE = ("--trace" in sys.argv)   # per-instruction ring buffer (slow)
unknown_imports = set()
TRACE = deque(maxlen=60)
TLSV = {"next": 1}     # emulated TLS slots
QPC = {"t": 0x10000}   # monotonic QueryPerformanceCounter (busy-wait loops need it)
THREADS = []           # captured (start_routine, param) from CreateThread
BLOCK_LIMIT = 120_000_000   # raised: real serialization does heavy bounded LUT loops

def halloc(n, align=16):
    global heap_ptr
    p = (heap_ptr + align-1) & ~(align-1)
    heap_ptr = p + n
    return p

def make_shims(uc, name_by_hookaddr):
    def rd(a,n): return uc.mem_read(a,n)
    def wr(a,b): uc.mem_write(a,bytes(b))
    def u32(a): return struct.unpack("<I",uc.mem_read(a,4))[0]
    def w32(a,v): uc.mem_write(a,struct.pack("<I",v&0xffffffff))
    def args(n):
        sp = uc.reg_read(UC_X86_REG_ESP)
        return [u32(sp+4+4*i) for i in range(n)]

    def shim(name):
        global NEXT_HANDLE
        a = args(8)   # read up to 8; use what we need
        if name in ("ExitProcess","TerminateProcess","abort","_invoke_watson"):
            print("  [%s] abort path. args=%s" % (name, [hex(x) for x in a[:3]]))
            ebp = uc.reg_read(UC_X86_REG_EBP)
            print("    --- EBP frame walk (caller chain) ---")
            for _ in range(20):
                if ebp < 0x1000 or ebp > 0x300000: break
                try:
                    ret = u32(ebp+4); nxt = u32(ebp)
                except: break
                print("      ret=0x%08x" % ret)
                if nxt <= ebp: break
                ebp = nxt
            uc.emu_stop()
            return 0
        if name in ("GetProcessHeap",): return 0x00CA0000
        if name == "HeapAlloc":
            return halloc(a[2])
        if name == "HeapReAlloc":
            newp = halloc(a[3])
            if a[2]:
                try: wr(newp, rd(a[2], min(a[3],0x10000)))
                except: pass
            return newp
        if name in ("HeapFree","HeapSize"): return 1
        if name in ("VirtualAlloc",):
            sz = a[1] or 0x1000
            return halloc(sz, 0x1000)
        if name in ("VirtualFree","VirtualProtect"): return 1
        if name == "CreateThread":
            THREADS.append((a[2], a[3]))   # (start_routine, parameter)
            print("  [CreateThread] start=0x%x param=0x%x" % (a[2], a[3]))
            return 0x00AB0000 + len(THREADS)   # fake handle
        if name in ("WaitForSingleObject","WaitForSingleObjectEx"): return 0  # signaled
        if name in ("GetExitCodeThread",):
            if a[1]: w32(a[1], 0)
            return 1
        if name == "CreateFileW" or name == "CreateFileA":
            NEXT_HANDLE += 1
            FILES[NEXT_HANDLE] = FakeFile(rcvp_bytes)
            return NEXT_HANDLE
        if name == "GetFileType": return 1   # FILE_TYPE_DISK
        if name in ("GetFileSizeEx",):
            f = FILES.get(a[0])
            if f and a[1]:
                w32(a[1], len(f.data)); w32(a[1]+4, 0)
            return 1
        if name == "GetFileSize":
            f = FILES.get(a[0]);
            if a[1]: w32(a[1],0)
            return len(f.data) if f else 0xFFFFFFFF
        if name == "SetFilePointerEx":
            f = FILES.get(a[0])
            if f is not None:
                lo=a[1]; meth=a[3]
                if meth==0: f.pos=lo
                elif meth==1: f.pos+=lo
                elif meth==2: f.pos=len(f.data)+ (lo if lo<0x80000000 else lo-(1<<32))
                if a[4]: w32(a[4],f.pos); w32(a[4]+4,0)
            return 1
        if name == "SetFilePointer":
            f = FILES.get(a[0])
            if f is not None:
                meth=a[3]; lo=a[1]
                if meth==0: f.pos=lo
                elif meth==1: f.pos+=lo
                elif meth==2: f.pos=len(f.data)
            return f.pos if f else 0xFFFFFFFF
        if name == "ReadFile":
            f = FILES.get(a[0])
            if f is None:
                if a[3]: w32(a[3],0)
                return 0
            n = a[2]; chunk = f.data[f.pos:f.pos+n]; f.pos += len(chunk)
            wr(a[1], chunk)
            if a[3]: w32(a[3], len(chunk))
            return 1
        if name in ("WriteFile",):
            try: WRITES.append(bytes(rd(a[1], a[2])))
            except: pass
            if a[3]: w32(a[3], a[2])
            return 1
        if name == "CloseHandle":
            FILES.pop(a[0], None); return 1
        if name in ("GetFileAttributesW","GetFileAttributesA"):
            return 0x80   # FILE_ATTRIBUTE_NORMAL
        if name == "GetLastError": return 0
        if name in ("SetLastError",): return 0
        if name in ("GetCurrentThreadId","GetCurrentProcessId"): return 0x1337
        if name in ("GetCurrentProcess","GetCurrentThread"): return 0xFFFFFFFF
        if name == "TlsAlloc":
            idx = TLSV["next"]; TLSV["next"] += 1; TLSV[idx] = 0; return idx
        if name == "TlsGetValue": return TLSV.get(a[0], 0)
        if name == "TlsSetValue": TLSV[a[0]] = a[1]; return 1
        if name == "TlsFree": TLSV.pop(a[0], None); return 1
        if name in ("QueryPerformanceCounter",):
            # MUST advance monotonically: the DLL has busy-wait timing loops that
            # spin until (QPC_now - QPC_start) exceeds a target. A constant value
            # = infinite loop. Step by a large delta so any wait completes fast.
            QPC["t"] += 0x4000000
            if a[0]: w32(a[0], QPC["t"] & 0xffffffff); w32(a[0]+4, QPC["t"] >> 32)
            return 1
        if name in ("QueryPerformanceFrequency",):
            if a[0]: w32(a[0],1000000); w32(a[0]+4,0)
            return 1
        if name == "GetTickCount": return 0x10000
        if name == "GetSystemTimeAsFileTime":
            if a[0]: w32(a[0],0); w32(a[0]+4,0)
            return 0
        if name in ("EnterCriticalSection","LeaveCriticalSection","DeleteCriticalSection",
                    "InitializeCriticalSection"): return 0
        if name in ("InitializeCriticalSectionAndSpinCount","InitializeCriticalSectionEx"): return 1
        if name in ("EncodePointer","DecodePointer"):
            ck = u32(0x102785d4)
            return a[0] ^ ck
        if name in ("GetModuleHandleW","GetModuleHandleA"): return IMAGE_BASE
        if name == "GetModuleHandleExW":
            if a[2]: w32(a[2], IMAGE_BASE)
            return 1
        if name == "GetProcAddress": return 0
        if name in ("LoadLibraryW","LoadLibraryExW"): return 0xD0000000
        if name == "FreeLibrary": return 1
        if name in ("IsDebuggerPresent","IsProcessorFeaturePresent"): return 0
        if name == "InitializeSListHead":
            if a[0]: w32(a[0],0); w32(a[0]+4,0)
            return 0
        if name == "SetUnhandledExceptionFilter": return 0
        if name in ("OutputDebugStringW","OutputDebugStringA"): return 0
        if name == "MultiByteToWideChar":
            return a[5] if a[5] else 1
        if name == "WideCharToMultiByte":
            return a[5] if a[5] else 1
        if name in ("GetACP",): return 1252    # SBCS (avoid DBCS lead-byte path)
        if name in ("GetOEMCP",): return 437
        if name == "IsValidCodePage": return 1
        if name == "GetCPInfo":
            if a[1]:
                wr(a[1], struct.pack("<I",1) + b"?\x00" + b"\x00"*12)  # MaxCharSize=1
            return 1
        if name == "GetStdHandle": return 0x100 + a[0]
        if name == "GetUserDefaultLCID": return 0x409
        if name in ("IsValidLocale","IsValidCodePage"): return 1
        if name == "EnumSystemLocalesW": return 1     # skip callback enumeration
        if name in ("GetLocaleInfoW","GetLocaleInfoA"): return 1
        if name in ("LCMapStringW","LCMapStringA","CompareStringW"): return 1
        if name == "GetTimeZoneInformation": return 0
        if name in ("GetStringTypeW","GetStringTypeA"): return 1
        if name in ("FlushFileBuffers","SetStdHandle","SetEndOfFile"): return 1
        if name in ("WriteConsoleW","GetConsoleMode","GetConsoleCP"): return 1
        if name in ("GetCommandLineA","GetCommandLineW"): return 0
        if name in ("GetEnvironmentStringsW",): return 0
        if name in ("FreeEnvironmentStringsW","SetEnvironmentVariableA"): return 1
        if name == "AreFileApisANSI": return 1
        if name == "GetModuleFileNameW" or name == "GetModuleFileNameA":
            return 0
        if name == "GetVersionExW" or name == "GetVersionExA":
            # Fill OSVERSIONINFO(EX) = Windows 7 (6.1.7601), platform NT. The CRT
            # gates static init on this; an unfilled buffer -> bad branch -> C++ throw.
            if a[0]:
                w32(a[0]+0x04, 6)       # dwMajorVersion
                w32(a[0]+0x08, 1)       # dwMinorVersion
                w32(a[0]+0x0c, 7601)    # dwBuildNumber
                w32(a[0]+0x10, 2)       # dwPlatformId = VER_PLATFORM_WIN32_NT
                # szCSDVersion left zeroed; wServicePackMajor/Minor (EX) = 0
            return 1
        if name == "GetVersion":
            return 0x23F00206          # 6.1, build hi word
        if name in ("RaiseException",):
            print("  [RaiseException] code=0x%x flags=0x%x" % (a[0], a[1]))
            ebp = uc.reg_read(UC_X86_REG_EBP)
            for _ in range(16):
                if not (0x1000 < ebp < 0x30000000): break
                try: ret=u32(ebp+4); nxt=u32(ebp)
                except: break
                print("      ret=0x%08x" % ret)
                if nxt<=ebp: break
                ebp=nxt
            uc.emu_stop(); return 0
        # network / detect (we want serialization only; pretend present/running)
        if name == "_Nic_IsSenderRunning@0": return 1
        if name == "_Nic_GetNetAdapterCount@8":
            if a[1]: w32(a[1], 1)
            return 1
        if name in ("htons","ntohs"): return ((a[0]&0xff)<<8)|((a[0]>>8)&0xff)
        if name in ("htonl","ntohl"):
            v=a[0]; return ((v&0xff)<<24)|((v&0xff00)<<8)|((v>>8)&0xff00)|((v>>24)&0xff)
        if name == "_Nic_Write@8":
            ptr,ln = a[0],a[1]
            try: buf = bytes(rd(ptr, ln))
            except: buf = b""
            nic_writes.append(buf)
            print("  [Nic_Write] ptr=0x%x len=%d : %s" % (ptr, ln, buf[:32].hex()))
            return 0   # success
        if name == "_Nic_Read@20":
            # serve a positive ack. args: (?, bufptr, buflen, ...). Put status 0x84.
            for ap in a[:5]:
                pass
            return 0
        if name == "_Nic_ClearReadCache@0": return 0
        if name == "_Nic_SetBlockFlags@4": return 0
        if name == "gethostname":
            if a[0] and a[1]: wr(a[0], b"localhost\x00")
            return 0
        if name == "gethostbyname":
            return 0    # NULL hostent -> caller falls back to adapter enumeration
        if name == "CoCreateGuid":
            if a[0]: wr(a[0], b"\x00"*16)
            return 0
        # default
        if name not in ARGC and name not in CDECL:
            unknown_imports.add(name)
        return 0
    return shim


# ----------------------------------------------------------------- GDT / FS
def gdt_entry(base, limit, access, flags):
    to=0
    to |= limit & 0xffff
    to |= (base & 0xffffff) << 16
    to |= (access & 0xff) << 40
    to |= ((limit >> 16) & 0xf) << 48
    to |= (flags & 0xf) << 52
    to |= ((base >> 24) & 0xff) << 56
    return struct.pack("<Q", to)

def setup_fs(uc):
    # Full flat GDT: idx1 flat code, idx2 flat data, idx3 FS(base=TEB). Reload ALL
    # segment selectors so SS/DS/CS/ES stay flat 32-bit and FS points at the TEB.
    uc.mem_map(GDT_BASE, 0x1000)
    uc.mem_write(GDT_BASE + 8*1, gdt_entry(0,        0xfffff, 0x9b, 0xc))  # code
    uc.mem_write(GDT_BASE + 8*2, gdt_entry(0,        0xfffff, 0x93, 0xc))  # data
    uc.mem_write(GDT_BASE + 8*3, gdt_entry(TEB_BASE, 0xfffff, 0x93, 0xc))  # fs
    uc.reg_write(UC_X86_REG_GDTR, (0, GDT_BASE, 8*4-1, 0))
    sel_code, sel_data, sel_fs = 0x08, 0x10, 0x18
    uc.reg_write(UC_X86_REG_CS, sel_code)
    uc.reg_write(UC_X86_REG_DS, sel_data)
    uc.reg_write(UC_X86_REG_ES, sel_data)
    uc.reg_write(UC_X86_REG_SS, sel_data)
    uc.reg_write(UC_X86_REG_GS, sel_data)
    uc.reg_write(UC_X86_REG_FS, sel_fs)
    # TEB minimal
    uc.mem_map(TEB_BASE, 0x4000)
    def w(off,val): uc.mem_write(TEB_BASE+off, struct.pack("<I",val&0xffffffff))
    w(0x00, 0xFFFFFFFF)        # SEH chain end
    w(0x04, STACK_TOP)         # stack base
    w(0x08, STACK_BASE)        # stack limit
    w(0x18, TEB_BASE)          # TEB self
    w(0x30, TEB_BASE+0x2000)   # PEB ptr (fake)
    w(0x2c, TEB_BASE+0x1000)   # TLS array


def load_pe(uc):
    pe = pefile.PE(DLL, fast_load=True); pe.parse_data_directories()
    data = open(DLL,"rb").read()
    # map headers
    hdr_sz = (pe.OPTIONAL_HEADER.SizeOfHeaders + 0xfff) & ~0xfff
    uc.mem_map(IMAGE_BASE, hdr_sz)
    uc.mem_write(IMAGE_BASE, data[:pe.OPTIONAL_HEADER.SizeOfHeaders])
    for s in pe.sections:
        va = IMAGE_BASE + s.VirtualAddress
        vsz = max(s.Misc_VirtualSize, s.SizeOfRawData)
        vsz = (vsz + 0xfff) & ~0xfff
        uc.mem_map(va, vsz, UC_PROT_ALL)
        raw = data[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
        uc.mem_write(va, raw)
    # exports
    base=pe.OPTIONAL_HEADER.ImageBase
    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if e.name: EXPORTS[e.name.decode()] = base + e.address
    return pe


def patch_imports(uc, pe):
    name_by_hook = {}
    argc_by_hook = {}
    cdecl_by_hook = {}
    h = HOOK_BASE
    for d in pe.DIRECTORY_ENTRY_IMPORT:
        dll = d.dll.decode()
        for imp in d.imports:
            nm = imp.name.decode() if imp.name else ("%s_ord%d"%(dll,imp.ordinal))
            sentinel = h; h += 4
            uc.mem_write(imp.address, struct.pack("<I", sentinel))
            name_by_hook[sentinel] = nm
            # argc: dict, else decorated @N, else default 0
            if nm in ARGC: argc_by_hook[sentinel] = ARGC[nm]
            elif "@" in nm:
                try: argc_by_hook[sentinel] = int(nm.split("@")[-1])//4
                except: argc_by_hook[sentinel] = 0
            else: argc_by_hook[sentinel] = 0
            cdecl_by_hook[sentinel] = (nm in CDECL)
    return name_by_hook, argc_by_hook, cdecl_by_hook


def main():
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    uc.mem_map(STACK_BASE, STACK_SIZE)
    uc.mem_map(HEAP_BASE, HEAP_SIZE)
    uc.mem_map(HOOK_BASE, HOOK_SIZE)          # import sentinels
    END_ADDR = HOOK_BASE + HOOK_SIZE - 0x10   # return sentinel
    setup_fs(uc)
    pe = load_pe(uc)
    name_by_hook, argc_by_hook, cdecl_by_hook = patch_imports(uc, pe)
    shim = make_shims(uc, name_by_hook)

    def hook_code(uc, address, size, ud):
        if HOOK_BASE <= address < HOOK_BASE+HOOK_SIZE and address != END_ADDR:
            nm = name_by_hook.get(address, "?%x"%address)
            sp = uc.reg_read(UC_X86_REG_ESP)
            ret = struct.unpack("<I", uc.mem_read(sp,4))[0]
            rv = shim(nm)
            argc = argc_by_hook.get(address,0)
            if trace_imports and nm not in ("HeapAlloc","HeapFree","HeapReAlloc","GetLastError","SetLastError","TlsGetValue","EnterCriticalSection","LeaveCriticalSection"):
                print("    <imp> %-28s -> 0x%x" % (nm, rv&0xffffffff))
            newsp = sp + 4 + (0 if cdecl_by_hook.get(address) else argc*4)
            uc.reg_write(UC_X86_REG_ESP, newsp)
            uc.reg_write(UC_X86_REG_EAX, rv & 0xffffffff)
            uc.reg_write(UC_X86_REG_EIP, ret)
    uc.hook_add(UC_HOOK_CODE, hook_code, begin=HOOK_BASE, end=HOOK_BASE+HOOK_SIZE)

    # Bypass the spin-mutex acquire (fcn.101f090e): always "acquire" and return,
    # so the single-threaded save path doesn't deadlock on a never-released lock.
    def hook_lock(uc, address, size, ud):
        ecx = uc.reg_read(UC_X86_REG_ECX)
        uc.mem_write(ecx, struct.pack("<I", 1))
        sp = uc.reg_read(UC_X86_REG_ESP)
        ret = struct.unpack("<I", uc.mem_read(sp,4))[0]
        uc.reg_write(UC_X86_REG_ESP, sp+4)
        uc.reg_write(UC_X86_REG_EIP, ret)
    uc.hook_add(UC_HOOK_CODE, hook_lock, begin=0x101f090e, end=0x101f090e)

    # Neutralize std::recursive_mutex::lock (fcn.101d67c6, __cdecl(mtx,flag)) and
    # its unlock (fcn.101d6a64). Their real acquire (0x101de064) throws a C++
    # std::system_error because the underlying Win32 sync primitive was never
    # initialized under emulation. We're single-threaded, so lock/unlock are no-ops.
    # Caller is cdecl (cleans its own args) -> we only pop the return address.
    def hook_noop_ret0(uc, address, size, ud):
        sp = uc.reg_read(UC_X86_REG_ESP)
        ret = struct.unpack("<I", uc.mem_read(sp,4))[0]
        uc.reg_write(UC_X86_REG_ESP, sp+4)
        uc.reg_write(UC_X86_REG_EAX, 0)
        uc.reg_write(UC_X86_REG_EIP, ret)
    for _addr in (0x101d67c6, 0x101d6a64):
        uc.hook_add(UC_HOOK_CODE, hook_noop_ret0, begin=_addr, end=_addr)

    if DEBUG_TRACE:
        def hook_trace(uc, address, size, ud):
            TRACE.append(address)
        uc.hook_add(UC_HOOK_CODE, hook_trace, begin=IMAGE_BASE, end=IMAGE_BASE+0x300000)

    # block watchdog: detect runaway loops without per-insn cost
    blk = {"n":0, "last":0, "hist":deque(maxlen=40)}
    def hook_block(uc, address, size, ud):
        blk["n"] += 1; blk["last"] = address; blk["hist"].append(address)
        if blk["n"] > BLOCK_LIMIT:
            print("    [WATCHDOG] %d blocks, spinning near 0x%x" % (blk["n"], address))
            print("      recent blocks:", [hex(x) for x in blk["hist"]])
            uc.emu_stop()
    uc.hook_add(UC_HOOK_BLOCK, hook_block)

    def dump_trace():
        print("    --- last %d instrs ---" % len(TRACE))
        for ad in list(TRACE):
            print("      0x%08x" % ad)

    def hook_mem_invalid(uc, access, address, size, value, ud):
        # access: 19=READ_UNMAPPED 20=WRITE_UNMAPPED 21=FETCH_UNMAPPED
        eip = uc.reg_read(UC_X86_REG_EIP)
        sp = uc.reg_read(UC_X86_REG_ESP)
        if access == 21 or address < 0x10000:   # bad fetch OR null-page deref = real bug
            stk = struct.unpack("<4I", uc.mem_read(sp,16))
            print("    [FAULT acc=%d] target=0x%x EIP=0x%x ESP=0x%x stack=%s" %
                  (access, address, eip, sp, [hex(x) for x in stk]))
            dump_trace()
            return False
        page = address & ~0xfff
        try:
            uc.mem_map(page, 0x1000)
            uc.mem_write(page, b"\x00"*0x1000)
            return True
        except Exception as ex:
            print("    [mem-invalid FATAL] 0x%x acc=%d %s" % (address,access,ex))
            return False
    uc.hook_add(UC_HOOK_MEM_INVALID, hook_mem_invalid)

    def call(addr, args, label="", ecx=None):
        sp = STACK_TOP
        for a in reversed(args):
            sp -= 4; uc.mem_write(sp, struct.pack("<I", a & 0xffffffff))
        sp -= 4; uc.mem_write(sp, struct.pack("<I", END_ADDR))
        uc.reg_write(UC_X86_REG_ESP, sp)
        if ecx is not None: uc.reg_write(UC_X86_REG_ECX, ecx)
        uc.reg_write(UC_X86_REG_EIP, addr)
        print("\n=== CALL %s @0x%x args=%s ===" % (label, addr, [hex(x) for x in args]))
        try:
            uc.emu_start(addr, END_ADDR, timeout=280*1000000, count=0)
        except UcError as ex:
            eip = uc.reg_read(UC_X86_REG_EIP)
            print("  !! UcError %s at EIP 0x%x" % (ex, eip))
            return None
        eip = uc.reg_read(UC_X86_REG_EIP)
        if eip != END_ADDR:
            print("  !! stopped early at EIP 0x%x (timeout/watchdog/stop)" % eip)
            return None
        rv = uc.reg_read(UC_X86_REG_EAX)
        print("  -> returned 0x%x" % rv)
        return rv

    # Bypass fragile CRT startup. The /GS cookie global already holds its default
    # (.data), used symmetrically in prologue/epilogue, so stack checks pass.
    # Manually construct the singleton, then pre-set the export lazy-guard so the
    # wrappers skip their own ctor+atexit and go straight to dispatch.
    global trace_imports
    trace_imports = False
    call(0x100fac00, [], "singleton ctor 0x100fac00")
    uc.mem_write(0x1028a670, struct.pack("<I", 1))   # guard bit set
    # CRT locale/feature-probe globals: encoded fn-pointers that real CRT init
    # would have populated. Set them = the /GS cookie so the probe decodes to 0
    # ("feature absent") and skips its indirect call. Harmless for byte output.
    cookie = struct.unpack("<I", uc.mem_read(0x102785d4,4))[0]
    # encoded fn-pointer globals (CRT feature probes + Fls-wrapper fallbacks).
    # Set = cookie so they decode to 0 -> skip indirect call / fall back to Tls*.
    # Scan the image for the "encoded fn-pointer" idiom:
    #   mov eax,[g]; xor eax,[cookie]; je skip; ... call eax
    # and set every such g = cookie so it decodes to 0 -> "handler absent/default".
    _img = open(DLL,"rb").read()
    _xor = b"\x33\x05\xd4\x85\x27\x10"
    enc_globals = set([0x1028a8d4]); _i = 0
    while True:
        j = _img.find(_xor, _i)
        if j < 0: break
        g = None
        if j>=5 and _img[j-5]==0xA1: g = struct.unpack("<I",_img[j-4:j])[0]
        elif j>=6 and _img[j-6]==0x8B and _img[j-5]==0x05: g = struct.unpack("<I",_img[j-4:j])[0]
        if g and 0x10278000 <= g < 0x1028c000 and b"\xff\xd0" in _img[j+6:j+52]:
            enc_globals.add(g)
        _i = j+1
    for g in enc_globals:
        uc.mem_write(g, struct.pack("<I", cookie))
    print("patched %d encoded-fnptr globals" % len(enc_globals))
    uc.mem_write(0x10289900, struct.pack("<I", 0x00CA0000))  # __acrt_heap handle
    # CRT lock table at 0x102784a8 (lockid*8). Normally bootstrapped by _initterm.
    # Pre-fill so locks look already-created (EnterCriticalSection is a no-op),
    # avoiding the guard-lock creation recursion.
    for i in range(128):
        cs = halloc(24)
        uc.mem_write(0x102784a8 + 8*i, struct.pack("<I", cs))
    trace_imports = True

    def u32(a): return struct.unpack("<I", uc.mem_read(a,4))[0]

    # 1) Materialise CReceiverOP via the singleton getter (vtable+0xac = 0x10102b40).
    crop = call(0x10102b40, [], "getter->CReceiverOP", ecx=0x1028a680)
    print("CReceiverOP = 0x%x" % (crop or 0))
    codec = u32(crop + 8)
    print("codec ([CReceiverOP+8]) = 0x%x" % codec)

    # 2) Deserialize the .rcvp straight from a memory buffer (bypasses ifstream):
    #    fcn.100945f0(this=codec, buf, size, 0)
    buf = halloc(len(rcvp_bytes)); uc.mem_write(buf, rcvp_bytes)
    r = call(0x100945f0, [buf, len(rcvp_bytes), 0], "deserialize .rcvp", ecx=codec)
    print("\ndeserialize result: %s (>=0 = success)" %
          (hex(r) if r is not None else "FAULT"))

    def w32(a,v): uc.mem_write(a, struct.pack("<I", v & 0xffffffff))

    # 2b) Build the DISPLAY config. InitFromFile = load(fcn.10090a80, the failing
    #     ifstream) THEN fcn.101a8370(this=CReceiverOP) which converts the loaded
    #     params into the display/send structures. Our shortcut deserialize already
    #     populated the save codec, so we skip the broken file load and call the
    #     display-builder directly -> GetSendCMDData should then emit real frames.
    rB = call(0x101a8370, [], "build display cfg (fcn.101a8370)", ecx=crop)
    print("  build display cfg -> %s" % (hex(rB) if rB is not None else "FAULT"))

    # 2c) data_emu generator = singleton.vtable[0x54] = fcn.100fbe20(this=singleton,
    #     bigDataObj). It writes data_emu.txt with the EXACT wire bytes per frame.
    #     We don't know which object is bigDataObj (~0xe570 B), so try candidates
    #     and capture WriteFile output; the right one yields valid VHDL w/ real bytes.
    cand = {
        "codec[crop+8]": u32(crop+8),
        "[crop+c]":      u32(crop+0xc),
        "[crop+10]":     u32(crop+0x10),
        "crop":          crop,
        "singleton":     0x1028a680,
    }
    for nm, obj in cand.items():
        WRITES.clear()
        print("\n--- data_emu gen with bigDataObj=%s (0x%x) ---" % (nm, obj))
        call(0x100fbe20, [obj], "gen(%s)"%nm, ecx=0x1028a680)
        total = sum(len(w) for w in WRITES)
        print("    WriteFile bytes captured: %d in %d calls" % (total, len(WRITES)))
        if total:
            blob = b"".join(WRITES)
            fn = "/home/muse/Desktop/LED/re/emu/data_emu_%s.txt" % nm.replace("[","").replace("]","").replace("+","")
            open(fn,"wb").write(blob)
            print("    wrote %s ; head: %r" % (fn, blob[:120]))

    # --- diagnostic: SaveToDevice impl reads [CReceiverOP+4]=sender, then
    #     sender.vtable[0x94] -> transport (null here -> error 0xe0830041).
    sender = u32(crop+4); svt = u32(sender) if sender else 0
    fn94 = u32(svt+0x94) if svt else 0
    print("DIAG sender=[crop+4]=0x%x vtable=0x%x  vtable[0x94]=0x%x" % (sender, svt, fn94))
    print("DIAG config=[crop+8 codec? +c?]: [crop+4]=0x%x [crop+8]=0x%x [crop+c]=0x%x [crop+10]=0x%x"
          % (u32(crop+4), u32(crop+8), u32(crop+0xc), u32(crop+0x10)))

    # 3) GetSaveCMDData: build the frame records into a caller buffer.
    REC = 0x60c; NREC = 0x820
    recbuf = halloc(REC*NREC); uc.mem_write(recbuf, b"\x00"*(REC*NREC))
    out = halloc(0x40); uc.mem_write(out, b"\x00"*0x40)
    w32(out+8, recbuf); w32(out+0xc, recbuf); w32(out+0x10, recbuf+REC*NREC)
    r3 = call(EXPORTS["_CLTReceiverGetSaveCMDData@4"], [out], "GetSaveCMDData")
    print("  GetSaveCMDData -> %s" % (hex(r3) if r3 is not None else "FAULT"))
    print("  out fields: [8]=0x%x [c]=0x%x [10]=0x%x" % (u32(out+8),u32(out+0xc),u32(out+0x10)))
    # walk records
    recs=[]
    for k in range(NREC):
        base = recbuf + k*REC
        ln = u32(base+0x600); code = u32(base+0x604)
        body = bytes(uc.mem_read(base, min(ln if 0<ln<=0x600 else 32, 0x600)))
        if ln==0 and code==0 and k>0: break
        recs.append((k,ln,code,body))
    print("  records found: %d" % len(recs))
    # save full records (header + body) to a file for offline analysis
    import json
    dump=[]
    for k in range(len(recs)):
        base = recbuf + k*REC
        full = bytes(uc.mem_read(base, REC))
        ln = struct.unpack_from("<I",full,0x600)[0]
        code = struct.unpack_from("<I",full,0x604)[0]
        dump.append({"k":k,"len":ln,"code":code,"body":full[:0x600].hex()})
    open("/home/muse/Desktop/LED/re/emu/records.json","w").write(json.dumps(dump))
    print("  wrote records.json (%d records)" % len(dump))
    for k,ln,code,body in recs[:6]:
        print("   rec[%02d] reccode=0x%x len=%-4d body=%s" % (k,code,ln,body[:24].hex()))
    globals()["_recs"]=recs; globals()["_recbuf"]=recbuf

    # 3b) GetSendCMDData (display/runtime path) - compare record format
    recbuf2 = halloc(REC*NREC); uc.mem_write(recbuf2, b"\x00"*(REC*NREC))
    out2 = halloc(0x40); uc.mem_write(out2, b"\x00"*0x40)
    w32(out2+0, recbuf2); w32(out2+4, recbuf2); w32(out2+8, recbuf2+REC*NREC)
    r4 = call(EXPORTS["_CLTReceiverGetSendCMDData@4"], [out2], "GetSendCMDData")
    print("  GetSendCMDData -> %s" % (hex(r4) if r4 is not None else "FAULT"))
    sdump=[]
    for k in range(NREC):
        base=recbuf2+k*REC
        ln=u32(base+0x600); code=u32(base+0x604)
        if ln==0 and code==0 and k>0: break
        full=bytes(uc.mem_read(base, REC))
        sdump.append({"k":k,"len":ln,"code":code,"body":full[:0x600].hex()})
    import json as _j
    open("/home/muse/Desktop/LED/re/emu/send_records.json","w").write(_j.dumps(sdump))
    print("  GetSendCMDData records: %d (wrote send_records.json)" % len(sdump))
    for r in sdump[:6]:
        print("   srec[%02d] reccode=0x%x len=%-4d body=%s"%(r["k"],r["code"],r["len"],r["body"][:48]))

    # 4) SaveToDevice spawns a worker thread (CreateThread) to do the send and
    #    spin-waits on it. We let it deadlock (watchdog stops it), capture the
    #    worker (start,param), then run the worker directly -> Nic_Write capture.
    print("\n=== SaveToDevice (spawns worker thread) ===")
    THREADS.clear(); nic_writes.clear()
    call(EXPORTS["_CLTReceiverRcvParamSaveToDevice@20"], [0,0,0,0,0], "SaveToDevice")
    print("  captured %d worker thread(s)" % len(THREADS))
    for ti,(start,param) in enumerate(THREADS):
        nic_writes.clear()
        print("  -- running worker[%d] start=0x%x param=0x%x --" % (ti,start,param))
        call(start, [param], "worker%d"%ti)
        print("     -> %d Nic_Write buffers" % len(nic_writes))
        wf=[]
        for i,b in enumerate(nic_writes):
            wf.append({"i":i,"len":len(b),"hex":b.hex()})
            if i<10: print("     nicw[%d] len=%d %s" % (i,len(b),b[:48].hex()))
        if nic_writes:
            import json as _j2
            open("/home/muse/Desktop/LED/re/emu/nic_writes.json","w").write(_j2.dumps(wf))
            print("     wrote nic_writes.json (%d frames)" % len(wf))

    if unknown_imports:
        print("\nUNKNOWN IMPORTS HIT (need argc/shim): %s" % sorted(unknown_imports))

    globals()["_uc"] = uc
    globals()["_crop"] = crop
    globals()["_codec"] = codec
    globals()["_call"] = call

if __name__ == "__main__":
    main()
