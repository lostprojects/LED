/* 32-bit harness: drive the SIMPLE 32-bit CLTDevice receiver path under Wine.
   The 32-bit model fetches the receiver manager directly (singleton.vtbl[0x94]) -
   no device-set vector, so it sidesteps the x64 blocker.
   Sequence: DefaultDetectAll -> GetCount -> (later) RcvParamInitFromFile -> SaveToDevice.
   Usage: h32.exe [detectArg1] [detectArg2]
*/
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>

typedef void (__stdcall *count_t)(int*, int);
typedef void (__stdcall *info_t)(int, char*, int, char*, int, char*);
typedef int  (__stdcall *ddetect_t)(int, int);
typedef int  (__stdcall *getcount_t)(void);
typedef int  (__stdcall *getname_t)(int, char*, int, char*, int);

static jmp_buf g_jb; static volatile int g_armed=0;
static LONG CALLBACK veh(PEXCEPTION_POINTERS ep){
    DWORD c=ep->ExceptionRecord->ExceptionCode;
    if(g_armed && (c & 0x10000000)){ g_armed=0; printf("  [VEH 0x%lx]\n",(unsigned long)c); longjmp(g_jb,1);}
    return EXCEPTION_CONTINUE_SEARCH;
}
#define GUARD(L,S) do{ if(setjmp(g_jb)==0){g_armed=1;S;g_armed=0;} else printf("  %s crashed\n",L);}while(0)

int main(int argc,char**argv){
    setvbuf(stdout,NULL,_IONBF,0);
    AddVectoredExceptionHandler(1,veh);
    HMODULE nic=LoadLibraryA("CLTNic.dll");
    HMODULE dev=LoadLibraryA("CLTDevice.dll");
    printf("nic=%p dev=%p GLE=%lu\n",(void*)nic,(void*)dev,(unsigned long)GetLastError());
    if(!dev){ printf("CLTDevice load failed\n"); return 1; }

    count_t   count = (count_t)  GetProcAddress(nic,"_Nic_GetNetAdapterCount@8");
    info_t    info  = (info_t)   GetProcAddress(nic,"_Nic_GetNetAdapterInfo@24");
    ddetect_t ddet  = (ddetect_t)GetProcAddress(dev,"_CLTReceiverDefaultDetectAll@8");
    getcount_t gc   = (getcount_t)GetProcAddress(dev,"_CLTReceiverGetCount@0");
    getname_t  gname= (getname_t)GetProcAddress(dev,"_CLTReceiverGetName@20");
    printf("count=%p info=%p ddet=%p gc=%p gname=%p\n",
           (void*)count,(void*)info,(void*)ddet,(void*)gc,(void*)gname);

    int n=-1; if(count) count(&n,1);
    printf("adapters=%d\n",n);
    for(int i=0;i<n && i<8;i++){
        char a[300]={0},b[300]={0},c[300]={0};
        if(info) info(i,a,260,b,260,c);
        printf("  [%d] '%s'\n",i,b);
    }

    int a1=argc>1?atoi(argv[1]):0, a2=argc>2?atoi(argv[2]):0;
    printf("DefaultDetectAll(%d,%d)...\n",a1,a2);
    int r=-12345; GUARD("ddet", r=ddet(a1,a2));
    printf("DefaultDetectAll ret=0x%x\n",(unsigned)r);

    Sleep(1000);
    int c=-12345; GUARD("gc", c=gc());
    printf("GetCount=%d\n",c);
    for(int i=0;i<c && i<16;i++){
        char nm[300]={0},tp[300]={0};
        if(gname){ GUARD("gname", gname(i,nm,260,tp,260)); printf("  rcv[%d] name='%s' type='%s'\n",i,nm,tp); }
    }
    return 0;
}
