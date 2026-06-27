/* Harness step 3: drive CLTReceiverDetectAll on the live card.
   Goal: receiver count > 0 (proves NIC binding + L2 detect), while tcpdump
   captures the 0x0700/0x0805 exchange on enx.
   Usage: h3.exe [targetIdx] [detectArg1] [detectArg2]
     targetIdx <0  -> skip CLTSetTargetDevice
   Crash recovery via a vectored exception handler + longjmp.
*/
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>

typedef void (*count_t)(int*, int);
typedef void (*info_t)(int, char*, int, char*, int, char*);
typedef int  (*detectall_t)(int, int, void*);
typedef int  (*getcount_t)(void);
typedef int  (*settarget_t)(int);

static jmp_buf g_jb;
static volatile int g_armed = 0;
static LONG CALLBACK veh(PEXCEPTION_POINTERS ep){
    DWORD code = ep->ExceptionRecord->ExceptionCode;
    if(g_armed && code != 0x406D1388 /*thread-name*/ && (code & 0x10000000)){
        printf("  [VEH] caught 0x%lx, recovering\n", code);
        g_armed = 0;
        longjmp(g_jb, 1);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
#define GUARD(label, stmt) do{ \
    if(setjmp(g_jb)==0){ g_armed=1; stmt; g_armed=0; } \
    else { printf("  %s recovered from crash\n", label); } \
  }while(0)

int main(int argc, char** argv){
    setvbuf(stdout, NULL, _IONBF, 0);
    AddVectoredExceptionHandler(1, veh);

    HMODULE nic = LoadLibraryA("CLTNic.dll");
    HMODULE dev = LoadLibraryA("CLTDevice.dll");
    printf("nic=%p dev=%p\n", (void*)nic, (void*)dev);
    if(!nic || !dev){ printf("load fail (GLE=%lu)\n", GetLastError()); return 1; }

    count_t     count     = (count_t)    GetProcAddress(nic,"Nic_GetNetAdapterCount");
    info_t      info      = (info_t)     GetProcAddress(nic,"Nic_GetNetAdapterInfo");
    detectall_t detectall = (detectall_t)GetProcAddress(dev,"CLTReceiverDetectAll");
    getcount_t  getcount  = (getcount_t) GetProcAddress(dev,"CLTReceiverGetCount");
    settarget_t settarget = (settarget_t)GetProcAddress(dev,"CLTSetTargetDevice");
    printf("detectall=%p getcount=%p settarget=%p\n",
           (void*)detectall,(void*)getcount,(void*)settarget);

    int n=-1; count(&n,1);
    printf("adapters=%d\n", n);
    for(int i=0;i<n && i<8;i++){
        char name[512]={0}, desc[512]={0}, ex[512]={0};
        info(i,name,260,desc,260,ex);
        printf("  [%d] desc='%s'\n", i, desc);
    }

    int tgt = argc>1 ? atoi(argv[1]) : -1;
    int a1  = argc>2 ? atoi(argv[2]) : 0;
    int a2  = argc>3 ? atoi(argv[3]) : 0;

    if(tgt>=0){
        printf("CLTSetTargetDevice(%d)\n", tgt);
        GUARD("settarget", settarget(tgt));
    }

    void* buf = VirtualAlloc(0, 0x40000, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE);
    printf("CLTReceiverDetectAll(%d,%d,buf=%p)...\n", a1,a2,buf);
    int r=-12345;
    GUARD("detectall", r = detectall(a1,a2,buf));
    printf("DetectAll ret=%d (0x%x)\n", r, (unsigned)r);

    Sleep(800);
    int c=-12345;
    GUARD("getcount", c = getcount());
    printf("CLTReceiverGetCount=%d\n", c);
    return 0;
}
