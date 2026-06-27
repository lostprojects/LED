/* h4: cold-start the 32-bit CLTNic sender, then drive CLTDevice detect.
   Sequence:
     enumerate adapters -> get id(name=GUID) + desc(enx) for idx 1
     Nic_NetAdapterIDExist(id?) / (desc?)  -> learn which string is the adapter ID
     Nic_CreateScreen(1, 64,64, <id>, 0,0)
     Nic_SenderStart(1) ; Nic_IsSenderRunning()
     CLTReceiverDefaultDetectAll(0,0) ; CLTReceiverGetCount()
   All guarded by VEH/longjmp; prints every return code. tcpdump runs alongside. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>

typedef int  (__stdcall *count_t)(int*, int);
typedef int  (__stdcall *info_t)(int, char*, int, char*, int, short*);
typedef int  (__stdcall *idexist_t)(char*);
typedef int  (__stdcall *createscreen_t)(int,int,int,int,int,int);
typedef int  (__stdcall *senderstart_t)(int);
typedef int  (__stdcall *issender_t)(void);
typedef int  (__stdcall *setsendnum_t)(int);
typedef int  (__stdcall *getscrcount_t)(int*);
typedef int  (__stdcall *iswpcap_t)(void);
typedef int  (__stdcall *ddetect_t)(int,int);
typedef int  (__stdcall *getcount_t)(void);

static jmp_buf g_jb; static volatile int g_armed=0;
static LONG CALLBACK veh(PEXCEPTION_POINTERS ep){
    DWORD c=ep->ExceptionRecord->ExceptionCode;
    if(g_armed && (c & 0x10000000)){ g_armed=0; printf("   [VEH 0x%lx]\n",(unsigned long)c); longjmp(g_jb,1);}
    return EXCEPTION_CONTINUE_SEARCH;
}
#define G(L,S) do{ if(setjmp(g_jb)==0){g_armed=1;S;g_armed=0;} else printf("   %s CRASHED\n",L);}while(0)

int main(int argc,char**argv){
    setvbuf(stdout,NULL,_IONBF,0);
    AddVectoredExceptionHandler(1,veh);
    HMODULE nic=LoadLibraryA("CLTNic.dll");
    HMODULE dev=LoadLibraryA("CLTDevice.dll");
    printf("nic=%p dev=%p\n",(void*)nic,(void*)dev);

    count_t        count   =(count_t)       GetProcAddress(nic,"_Nic_GetNetAdapterCount@8");
    info_t         info    =(info_t)        GetProcAddress(nic,"_Nic_GetNetAdapterInfo@24");
    idexist_t      idexist =(idexist_t)     GetProcAddress(nic,"_Nic_NetAdapterIDExist@4");
    createscreen_t cscreen =(createscreen_t)GetProcAddress(nic,"_Nic_CreateScreen@24");
    senderstart_t  sstart  =(senderstart_t) GetProcAddress(nic,"_Nic_SenderStart@4");
    issender_t     isrun   =(issender_t)    GetProcAddress(nic,"_Nic_IsSenderRunning@0");
    setsendnum_t   setnum  =(setsendnum_t)  GetProcAddress(nic,"_Nic_SetSendParamScreenNumber@4");
    getscrcount_t  gscr    =(getscrcount_t) GetProcAddress(nic,"_Nic_GetScreenCount@4");
    iswpcap_t      iswp    =(iswpcap_t)     GetProcAddress(nic,"_Nic_DetectIsInstallWinpCap@0");
    ddetect_t      ddet    =(ddetect_t)     GetProcAddress(dev,"_CLTReceiverDefaultDetectAll@8");
    getcount_t     gc      =(getcount_t)    GetProcAddress(dev,"_CLTReceiverGetCount@0");
    printf("idexist=%p cscreen=%p sstart=%p ddet=%p gc=%p\n",
           (void*)idexist,(void*)cscreen,(void*)sstart,(void*)ddet,(void*)gc);

    int n=-1; count(&n,1);
    printf("adapters=%d\n",n);
    char id[300]={0}, desc[300]={0}; short ty=0;
    for(int i=0;i<n && i<8;i++){
        char a[300]={0},b[300]={0}; short t=0;
        info(i,a,260,b,260,&t);
        printf("  [%d] id(name)='%s'  desc='%s'  type=%d\n",i,a,b,(int)t);
        if(i==1){ strncpy(id,a,299); strncpy(desc,b,299); ty=t; }
    }
    printf("\n-- using idx1: id='%s' desc='%s' type=%d --\n",id,desc,(int)ty);

    int r;
    r=-9; G("IsInstallWinpCap", r=iswp?iswp():-1); printf("Nic_DetectIsInstallWinpCap = %d\n",r);
    r=0x424242; G("idexist(id)",   r=idexist(id));   printf("NetAdapterIDExist(id)   = 0x%x\n",(unsigned)r);
    r=0x424242; G("idexist(desc)", r=idexist(desc)); printf("NetAdapterIDExist(desc) = 0x%x\n",(unsigned)r);

    /* CreateScreen(screenNo, w, h, RESERVED=0, enum0..3, enum0..3). No adapter arg.
       Sweep the two small enums from argv to find a combo the card reacts to. */
    int e4 = argc>1 ? atoi(argv[1]) : 0;
    int e5 = argc>2 ? atoi(argv[2]) : 0;
    printf("\nCreateScreen(1,64,64, 0, e4=%d, e5=%d)\n", e4, e5);
    r=0x424242; G("CreateScreen", r=cscreen(1,64,64,0,e4,e5));
    printf("Nic_CreateScreen = 0x%x\n",(unsigned)r);

    int sc=-9; G("GetScreenCount", gscr(&sc)); printf("Nic_GetScreenCount = %d\n",sc);

    r=0x424242; G("SetSendParamScreenNumber", r=setnum(1));
    printf("Nic_SetSendParamScreenNumber(1) = 0x%x\n",(unsigned)r);

    r=0x424242; G("SenderStart", r=sstart(1));
    printf("Nic_SenderStart(1)  = 0x%x\n",(unsigned)r);
    r=-9; G("IsSenderRunning", r=isrun());
    printf("Nic_IsSenderRunning = %d\n",r);

    Sleep(500);
    printf("\nCLTReceiverDefaultDetectAll(0,0)...\n");
    r=0x424242; G("DefaultDetectAll", r=ddet(0,0));
    printf("DefaultDetectAll = 0x%x\n",(unsigned)r);
    Sleep(1000);
    int c=-9; G("GetCount", c=gc());
    printf("CLTReceiverGetCount = %d\n",c);
    Sleep(1500); /* let any sender thread emit frames for the capture */
    return 0;
}
