/* cap.c (x64): hook CLTNic!Nic_Write, drive CLTDevice RcvParam config send.
   Captures every wire frame CLTDevice builds AND forwards it to the card via
   our own (proven) wpcap handle on enx. Bypasses CLTNic's sender/adapter wall. */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* ---- wpcap ---- */
typedef struct pcap_if { struct pcap_if *next; char *name; char *description; void *addr; unsigned int flags; } pcap_if_t;
typedef int   (*findalldevs_t)(pcap_if_t **, char *);
typedef void *(*openlive_t)(const char *, int, int, int, char *);
typedef int   (*sendpacket_t)(void *, const unsigned char *, int);

static void *g_pcap = NULL;
static sendpacket_t g_send = NULL;
static FILE *g_log = NULL;
static int g_n = 0;

/* x64: rcx=buf, edx=len */
static int my_Nic_Write(unsigned char *buf, int len){
    g_n++;
    int sr = -999;
    if(g_pcap && g_send) sr = g_send(g_pcap, buf, len);
    printf("  [Nic_Write #%d] len=%d send=%d  head=", g_n, len, sr);
    for(int i=0;i<len && i<16;i++) printf("%02x", buf[i]);
    printf("\n");
    if(g_log){ fprintf(g_log,"FRAME %d %d ",g_n,len);
        for(int i=0;i<len;i++) fprintf(g_log,"%02x",buf[i]);
        fprintf(g_log,"\n"); fflush(g_log); }
    return 0;
}

static void hook(void *target, void *dst){
    DWORD old;
    VirtualProtect(target, 16, PAGE_EXECUTE_READWRITE, &old);
    unsigned char *p = (unsigned char*)target;
    p[0]=0x48; p[1]=0xB8; memcpy(p+2,&dst,8);  /* mov rax, dst */
    p[10]=0xFF; p[11]=0xE0;                      /* jmp rax */
    FlushInstructionCache(GetCurrentProcess(), target, 16);
}

typedef int (*init_t)(const wchar_t*);
typedef int (*save_t)(int,int,int,int,int);
typedef int (*settarget_t)(int);

int main(int argc, char**argv){
    setvbuf(stdout,NULL,_IONBF,0);
    /* open pcap on enx */
    HMODULE wp = LoadLibraryA("wpcap.dll");
    findalldevs_t findall=(findalldevs_t)GetProcAddress(wp,"pcap_findalldevs");
    openlive_t    openlive=(openlive_t)GetProcAddress(wp,"pcap_open_live");
    g_send=(sendpacket_t)GetProcAddress(wp,"pcap_sendpacket");
    char eb[256]={0}; pcap_if_t *devs=NULL; char *npf=NULL;
    findall(&devs,eb);
    for(pcap_if_t*d=devs;d;d=d->next) if(d->description && !strcmp(d->description,"enx9c69d388d76e")) npf=_strdup(d->name);
    if(!npf){ printf("enx not found\n"); return 2; }
    g_pcap=openlive(npf,65536,1,50,eb);
    printf("pcap=%p (%s)\n", g_pcap, g_pcap?"OPEN":eb);

    HMODULE nic=LoadLibraryA("CLTNic.dll");
    HMODULE dev=LoadLibraryA("CLTDevice.dll");
    printf("nic=%p dev=%p\n",(void*)nic,(void*)dev);
    void *nw=(void*)GetProcAddress(nic,"Nic_Write");
    printf("Nic_Write=%p -> hooking\n", nw);
    hook(nw, (void*)my_Nic_Write);

    init_t init=(init_t)GetProcAddress(dev,"CLTReceiverRcvParamInitFromFile");
    save_t save=(save_t)GetProcAddress(dev,"CLTReceiverRcvParamSaveToDevice");
    settarget_t st=(settarget_t)GetProcAddress(dev,"CLTSetTargetDevice");
    printf("init=%p save=%p settarget=%p\n",(void*)init,(void*)save,(void*)st);

    g_log=fopen("Z:\\home\\muse\\Desktop\\LED\\re\\capture\\nicwrite_frames.txt","w");

    int ri=init(L"cfg.rcvp");
    printf("InitFromFile = %d (0x%x)\n", ri, (unsigned)ri);

    if(st){ int r=st(0); printf("CLTSetTargetDevice(0)=%d\n", r); }

    /* sweep SaveToDevice args; report Nic_Write count per call */
    int combos[][5] = { {0,0,0,0,0}, {1,0,0,0,0}, {0,1,0,0,0}, {1,1,1,1,1}, {0,0,1,0,0} };
    for(int c=0;c<5;c++){
        int before=g_n;
        int r=save(combos[c][0],combos[c][1],combos[c][2],combos[c][3],combos[c][4]);
        printf("SaveToDevice(%d,%d,%d,%d,%d) = %d (0x%x)  frames+=%d\n",
            combos[c][0],combos[c][1],combos[c][2],combos[c][3],combos[c][4],
            r,(unsigned)r, g_n-before);
        Sleep(300);
    }
    printf("total Nic_Write calls = %d\n", g_n);
    Sleep(500);
    return 0;
}
