/* Prove two-way Colorlight comms through Wine's wpcap bridge:
   open enx9c69d388d76e, send the 0x0700 detection frame, listen for 0x0805. */
#include <windows.h>
#include <stdio.h>
#include <string.h>

typedef struct pcap_if { struct pcap_if *next; char *name; char *description; void *addresses; unsigned int flags; } pcap_if_t;
typedef struct pcap_pkthdr { char ts[8]; unsigned int caplen; unsigned int len; } pcap_pkthdr_t;

typedef int   (*findalldevs_t)(pcap_if_t **, char *);
typedef void  (*freealldevs_t)(pcap_if_t *);
typedef void *(*open_live_t)(const char *, int, int, int, char *);
typedef int   (*sendpacket_t)(void *, const unsigned char *, int);
typedef int   (*next_ex_t)(void *, pcap_pkthdr_t **, const unsigned char **);
typedef void  (*close_t)(void *);

int main(void){
    HMODULE h = LoadLibraryA("wpcap.dll");
    if(!h){ printf("LOADFAIL\n"); return 1; }
    findalldevs_t findall = (findalldevs_t)GetProcAddress(h,"pcap_findalldevs");
    open_live_t   openlive= (open_live_t)GetProcAddress(h,"pcap_open_live");
    sendpacket_t  sendpkt = (sendpacket_t)GetProcAddress(h,"pcap_sendpacket");
    next_ex_t     nextex  = (next_ex_t)GetProcAddress(h,"pcap_next_ex");

    char errbuf[256]={0};
    pcap_if_t *devs=NULL;
    if(findall(&devs,errbuf)!=0){ printf("findall FAIL %s\n",errbuf); return 2; }
    char *npf=NULL;
    for(pcap_if_t *d=devs; d; d=d->next)
        if(d->description && strcmp(d->description,"enx9c69d388d76e")==0){ npf=_strdup(d->name); break; }
    if(!npf){ printf("enx not found\n"); return 3; }
    printf("opening %s\n", npf);

    void *p = openlive(npf, 65536, 1, 50, errbuf);
    if(!p){ printf("OPEN FAIL %s\n", errbuf); return 4; }
    printf("OPEN OK\n");

    /* build 271-byte detection frame */
    unsigned char f[271]; memset(f,0,sizeof f);
    unsigned char dst[6]={0x11,0x22,0x33,0x44,0x55,0x66};
    unsigned char src[6]={0x22,0x22,0x33,0x44,0x55,0x66};
    memcpy(f,dst,6); memcpy(f+6,src,6); f[12]=0x07; f[13]=0x00; f[16]=0;

    for(int i=0;i<5;i++){
        int r=sendpkt(p,f,sizeof f);
        printf("send #%d ret=%d\n", i, r);
        /* drain replies for ~1s */
        for(int k=0;k<20;k++){
            pcap_pkthdr_t *hdr; const unsigned char *data;
            int rc=nextex(p,&hdr,&data);
            if(rc==1 && hdr->caplen>=14){
                if(data[6]==0x22 && data[7]==0x22) continue; /* our own */
                if(data[12]==0x08){
                    printf("*** CARD REPLY ethertype 0x%02x%02x len=%u src=%02x:%02x:%02x:%02x:%02x:%02x\n",
                        data[12],data[13],hdr->caplen,data[6],data[7],data[8],data[9],data[10],data[11]);
                    printf("    fw=%d.%d\n", data[14+2], data[14+3]);
                    return 0;
                }
            }
        }
        Sleep(200);
    }
    printf("no 0x08xx reply seen\n");
    return 5;
}
