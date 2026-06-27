#include <windows.h>
#include <stdio.h>
typedef int (*iswp_t)(void);
typedef int (*count_t)(int*,int);
int main(void){
  setvbuf(stdout,NULL,_IONBF,0);
  HMODULE nic=LoadLibraryA("CLTNic.dll");
  printf("nic=%p GLE=%lu\n",(void*)nic,GetLastError());
  if(!nic) return 1;
  iswp_t iswp=(iswp_t)GetProcAddress(nic,"Nic_DetectIsInstallWinpCap");
  printf("iswp ptr=%p\n",(void*)iswp);
  if(iswp) printf("Nic_DetectIsInstallWinpCap = %d (0=installed/ok)\n", iswp());
  count_t cnt=(count_t)GetProcAddress(nic,"Nic_GetNetAdapterCount");
  int n=-1; if(cnt){ cnt(&n,1); printf("adapters=%d\n",n); }
  return 0;
}
