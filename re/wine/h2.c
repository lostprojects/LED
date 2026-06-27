/* Harness step 2: enumerate adapters with the REAL signatures from disasm.
   Nic_GetNetAdapterCount(int* out, BOOL refresh);
   Nic_GetNetAdapterInfo(int idx, char* name, int cp, char* desc, int cp2, char* extra); */
#include <windows.h>
#include <stdio.h>

typedef void (*count_t)(int*, int);
typedef void (*info_t)(int, char*, int, char*, int, char*);

int main(void){
    setvbuf(stdout,NULL,_IONBF,0);
    HMODULE nic = LoadLibraryA("CLTNic.dll");
    if(!nic){ printf("no CLTNic\n"); return 1; }
    count_t count = (count_t)GetProcAddress(nic,"Nic_GetNetAdapterCount");
    info_t  info  = (info_t) GetProcAddress(nic,"Nic_GetNetAdapterInfo");
    printf("count=%p info=%p\n",(void*)count,(void*)info);

    int n=-1;
    count(&n, 1);                 /* refresh=1 -> enumerate */
    printf("NetAdapterCount = %d\n", n);
    if(n<=0 || n>32){ printf("bad count, stop\n"); return 0; }

    for(int i=0;i<n;i++){
        char name[1024]={0}, desc[1024]={0}, extra[1024]={0};
        info(i, name, 260, desc, 260, extra);
        printf("Adapter[%d]\n  name='%.200s'\n  desc='%.200s'\n  extra='%.120s'\n",
               i, name, desc, extra);
    }
    return 0;
}
