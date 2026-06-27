/* Harness step 1: map the CLTNic adapter API (safe, low-arg probes). */
#include <windows.h>
#include <stdio.h>

int main(void){
    HMODULE nic = LoadLibraryA("CLTNic.dll");
    HMODULE dev = LoadLibraryA("CLTDevice.dll");
    printf("nic=%p dev=%p\n", (void*)nic, (void*)dev);
    if(!nic){ printf("no CLTNic\n"); return 1; }

    typedef int (*i_v)(void);
    typedef int (*i_i)(int);

    i_v winpcap = (i_v)GetProcAddress(nic,"Nic_DetectIsInstallWinpCap");
    i_v count   = (i_v)GetProcAddress(nic,"Nic_GetNetAdapterCount");
    printf("DetectIsInstallWinpCap=%p GetNetAdapterCount=%p\n",(void*)winpcap,(void*)count);

    if(winpcap){ printf("WinPcap installed? = %d\n", winpcap()); }
    int n = -999;
    if(count){ n = count(); printf("NetAdapterCount = %d\n", n); }

    /* Nic_GetNetAdapterInfo: unknown sig. Try (int idx, char* name1k, char* desc1k, char* id1k). */
    typedef int (*info_t)(int, char*, char*, char*);
    info_t info = (info_t)GetProcAddress(nic,"Nic_GetNetAdapterInfo");
    if(info && n>0 && n<32){
        for(int i=0;i<n;i++){
            char a[1024]={0}, b[1024]={0}, c[1024]={0};
            int r = info(i,a,b,c);
            printf("Adapter[%d] r=%d a='%.120s' b='%.120s' c='%.120s'\n", i, r, a, b, c);
        }
    } else {
        printf("info=%p (skipped)\n",(void*)info);
    }
    return 0;
}
