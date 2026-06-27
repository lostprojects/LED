/* probe.c (x64): like cap2.c (hook Nic_Write+Nic_Read onto our wpcap handle on
   enx) but ADDS the key dynamic experiment: call the device-manager refresh
   vtbl[0x10] (= vt[2]) DIRECTLY to try to populate the device list, then re-check
   the detect exports. Run "probe.exe" for read-only (no config write); run
   "probe.exe save" to also do step 4 (SaveToDevice) — only with the panel watched.

   Manager singleton: GetHwDeviceManager() returns 0x180374520 (the IDeviceManager).
   vt = *(void***)mgr;  vt[2] = vtbl+0x10 = refresh/detect populator (fcn.180154f70).
*/
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <setjmp.h>

static jmp_buf g_jb; static volatile int g_guard=0; static volatile unsigned long g_code=0;
static LONG CALLBACK veh(PEXCEPTION_POINTERS ep){
    if(g_guard){ g_code=ep->ExceptionRecord->ExceptionCode; longjmp(g_jb,1); }
    return EXCEPTION_CONTINUE_SEARCH;
}

typedef struct pcap_if { struct pcap_if *next; char *name; char *description; void *addr; unsigned int flags; } pcap_if_t;
typedef struct pcap_pkthdr { long long ts_sec; long long ts_usec; unsigned int caplen; unsigned int len; } pcap_pkthdr_t;
typedef int   (*findalldevs_t)(pcap_if_t **, char *);
typedef void *(*openlive_t)(const char *, int, int, int, char *);
typedef int   (*sendpacket_t)(void *, const unsigned char *, int);
typedef int   (*nextex_t)(void *, pcap_pkthdr_t **, const unsigned char **);

static void *g_pcap=NULL; static sendpacket_t g_send=NULL; static nextex_t g_next=NULL;
static FILE *g_log=NULL; static int g_nw=0, g_rd=0;

static int my_Nic_Write(unsigned char *buf, int len){
    g_nw++;
    int sr=-1; if(g_pcap&&g_send) sr=g_send(g_pcap,buf,len);
    printf("  [W#%d] len=%d snd=%d ",g_nw,len,sr);
    for(int i=0;i<len&&i<18;i++) printf("%02x",buf[i]); printf("\n");
    if(g_log){ fprintf(g_log,"W %d %d ",g_nw,len); for(int i=0;i<len;i++) fprintf(g_log,"%02x",buf[i]); fprintf(g_log,"\n"); fflush(g_log);}
    return 0;
}
/* public Nic_Read(rcx=a1,rdx=a2,r8=a3,r9=a4,[stack]=a5) */
static long long my_Nic_Read(unsigned char *a1, long long a2, long long a3, long long a4, long long a5){
    g_rd++;
    if(g_rd<=12) printf("  [R#%d] a1=%p a2=%lld a3=%lld a4=%lld a5=%lld\n",g_rd,(void*)a1,a2,a3,a4,a5);
    /* try to pull a card reply (src MAC 11:22:33:44:55:66) from our handle */
    if(g_pcap&&g_next&&a1){
        for(int k=0;k<10;k++){
            pcap_pkthdr_t *h; const unsigned char *d;
            int rc=g_next(g_pcap,&h,&d);
            if(rc==1 && h->caplen>=14 && d[6]==0x11 && d[7]==0x22){
                int n=h->caplen; if(a2>0 && n>(int)a2) n=(int)a2;
                memcpy(a1,d,n);
                if(g_rd<=12){ printf("     -> fed %d bytes (card reply) ",n);
                    for(int i=0;i<n&&i<18;i++) printf("%02x",d[i]); printf("\n"); }
                if(g_log){ fprintf(g_log,"R %d %d ",g_rd,n); for(int i=0;i<n;i++) fprintf(g_log,"%02x",d[i]); fprintf(g_log,"\n"); fflush(g_log);}
                return n;
            }
        }
    }
    return 0;
}
static void hook(void*t,void*dst){ DWORD o; VirtualProtect(t,16,PAGE_EXECUTE_READWRITE,&o);
    unsigned char*p=t; p[0]=0x48;p[1]=0xB8; memcpy(p+2,&dst,8); p[10]=0xFF;p[11]=0xE0;
    FlushInstructionCache(GetCurrentProcess(),t,16); }

typedef void* (*getmgr_t)(void);
typedef long long (*ref_t)(void*, long long);
typedef int (*init_t)(const wchar_t*);
typedef int (*save_t)(int,int,int,int,int);
typedef int (*detect_t)(int,int,void*);
typedef int (*ddetect_t)(int,int);
typedef int (*getcount_t)(void);
typedef int (*settarget_t)(int);

static getcount_t gc=NULL;
static void *g_mgr=NULL;

static long long call_refresh(ref_t ref, void*mgr, long long arg){
    long long r=-1;
    if(setjmp(g_jb)==0){ g_guard=1; r=ref(mgr,arg); g_guard=0; }
    else { g_guard=0; printf("  [refresh arg=%lld threw 0x%lx]\n",arg,(unsigned long)g_code); r=-2; }
    return r;
}

int main(int argc,char**argv){
    setvbuf(stdout,NULL,_IONBF,0);
    AddVectoredExceptionHandler(1, veh);
    int do_save = (argc>1 && !strcmp(argv[1],"save"));

    HMODULE wp=LoadLibraryA("wpcap.dll");
    findalldevs_t fa=(findalldevs_t)GetProcAddress(wp,"pcap_findalldevs");
    openlive_t ol=(openlive_t)GetProcAddress(wp,"pcap_open_live");
    g_send=(sendpacket_t)GetProcAddress(wp,"pcap_sendpacket");
    g_next=(nextex_t)GetProcAddress(wp,"pcap_next_ex");
    char eb[256]={0}; pcap_if_t*devs=NULL; char*npf=NULL; fa(&devs,eb);
    for(pcap_if_t*d=devs;d;d=d->next) if(d->description&&!strcmp(d->description,"enx9c69d388d76e")) npf=_strdup(d->name);
    if(!npf){printf("no enx\n");return 2;}
    g_pcap=ol(npf,65536,1,50,eb); printf("pcap=%p\n",g_pcap);

    HMODULE nic=LoadLibraryA("CLTNic.dll"), dev=LoadLibraryA("CLTDevice.dll");
    void*nw=(void*)GetProcAddress(nic,"Nic_Write"); void*nr=(void*)GetProcAddress(nic,"Nic_Read");
    printf("Nic_Write=%p Nic_Read=%p\n",nw,nr);
    hook(nw,(void*)my_Nic_Write); hook(nr,(void*)my_Nic_Read);

    getmgr_t getmgr=(getmgr_t)GetProcAddress(dev,"?GetHwDeviceManager@@YAPEAVIDeviceManager@@XZ");
    init_t init=(init_t)GetProcAddress(dev,"CLTReceiverRcvParamInitFromFile");
    save_t save=(save_t)GetProcAddress(dev,"CLTReceiverRcvParamSaveToDevice");
    detect_t det=(detect_t)GetProcAddress(dev,"CLTReceiverDetectAll");
    ddetect_t ddet=(ddetect_t)GetProcAddress(dev,"CLTReceiverDefaultDetectAll");
    gc=(getcount_t)GetProcAddress(dev,"CLTReceiverGetCount");
    settarget_t st=(settarget_t)GetProcAddress(dev,"CLTSetTargetDevice");
    g_log=fopen("Z:\\home\\muse\\Desktop\\LED\\re\\capture\\nicwrite_frames.txt","w");
    printf("getmgr=%p init=%p save=%p det=%p ddet=%p gc=%p st=%p\n",
        (void*)getmgr,(void*)init,(void*)save,(void*)det,(void*)ddet,(void*)gc,(void*)st);

    /* baseline detect-export error codes BEFORE refresh */
    printf("\n== BASELINE (before refresh) ==\n");
    if(ddet){ int r=ddet(0,0); printf("DefaultDetectAll=0x%x  GetCount=%d\n",(unsigned)r, gc?gc():-1); }

    /* ===== THE EXPERIMENT: call manager refresh vtbl[0x10] directly ===== */
    printf("\n== STEP 1/2: GetHwDeviceManager + refresh vt[2] ==\n");
    g_mgr = getmgr ? getmgr() : NULL;
    printf("mgr=%p\n",g_mgr);
    if(g_mgr){
        void**vt = *(void***)g_mgr;
        printf("vtbl=%p\n",(void*)vt);
        HMODULE base=GetModuleHandleA("CLTDevice.dll");
        printf("CLTDevice base=%p\n",(void*)base);
        printf("vt[2] (refresh) = %p   rva=0x%llx  (expect 0x154f70)\n",
            vt[2], (unsigned long long)((char*)vt[2]-(char*)base));
        ref_t ref=(ref_t)vt[2];
        for(long long arg=0; arg<=1; arg++){
            int wb=g_nw, rb=g_rd;
            printf("\n-- refresh(mgr, %lld) --\n",arg);
            long long rr=call_refresh(ref,g_mgr,arg);
            printf("refresh(%lld)=0x%llx (%lld)   Nic_Write+=%d Nic_Read+=%d  GetCount=%d\n",
                arg,(unsigned long long)rr,rr,g_nw-wb,g_rd-rb, gc?gc():-1);
            Sleep(400);
        }
    }

    /* ===== STEP 3: re-check the detect exports ===== */
    printf("\n== STEP 3: detect exports AFTER refresh ==\n");
    if(ddet){ int r=ddet(0,0); printf("DefaultDetectAll=0x%x  GetCount=%d\n",(unsigned)r, gc?gc():-1); }
    Sleep(200);
    void*b=VirtualAlloc(0,0x40000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(det){ int r=det(0,0,b); printf("DetectAll=0x%x  GetCount=%d\n",(unsigned)r, gc?gc():-1); }
    Sleep(200);

    /* ===== STEP 4: SaveToDevice (only if a device registered AND 'save' arg) ===== */
    int cnt = gc?gc():0;
    printf("\n== receiver count after detect = %d ==\n",cnt);
    if(!do_save){
        printf("(read-only mode; pass 'save' arg to attempt SaveToDevice)\n");
    } else {
        int ri=init(L"cfg.rcvp"); printf("InitFromFile=0x%x\n",(unsigned)ri);
        if(st){ printf("SetTargetDevice(0)=%d\n", st(0)); }
        printf("\n-- SaveToDevice sweep --\n");
        int combos[][5]={{0,0,0,0,0},{1,0,0,0,0},{0,1,0,0,0}};
        for(int c=0;c<3;c++){ int before=g_nw;
            int r=save(combos[c][0],combos[c][1],combos[c][2],combos[c][3],combos[c][4]);
            printf("Save(%d,%d,%d,%d,%d)=0x%x  W+=%d\n",combos[c][0],combos[c][1],combos[c][2],combos[c][3],combos[c][4],(unsigned)r,g_nw-before);
            Sleep(400);
        }
    }
    printf("\ntotal Nic_Write=%d  Nic_Read=%d\n",g_nw,g_rd);
    Sleep(500); return 0;
}
