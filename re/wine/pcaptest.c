/* Minimal probe: does Wine's wpcap.dll enumerate Linux interfaces?
   Loads wpcap.dll at runtime, calls pcap_findalldevs, prints names. */
#include <windows.h>
#include <stdio.h>

typedef struct pcap_addr { void *next; void *addr; void *netmask; void *broadaddr; void *dstaddr; } pcap_addr_t;
typedef struct pcap_if { struct pcap_if *next; char *name; char *description; pcap_addr_t *addresses; unsigned int flags; } pcap_if_t;

typedef int  (*findalldevs_t)(pcap_if_t **, char *);
typedef void (*freealldevs_t)(pcap_if_t *);

int main(void){
    HMODULE h = LoadLibraryA("wpcap.dll");
    if(!h){ printf("LOADFAIL wpcap.dll err=%lu\n", GetLastError()); return 1; }
    findalldevs_t findall = (findalldevs_t)GetProcAddress(h,"pcap_findalldevs");
    freealldevs_t freeall = (freealldevs_t)GetProcAddress(h,"pcap_freealldevs");
    if(!findall){ printf("NO pcap_findalldevs export\n"); return 2; }
    char errbuf[256]={0};
    pcap_if_t *devs=NULL;
    int r = findall(&devs, errbuf);
    if(r!=0){ printf("findalldevs FAILED r=%d err=%s\n", r, errbuf); return 3; }
    int n=0;
    for(pcap_if_t *d=devs; d; d=d->next){
        printf("DEV[%d] name=%s desc=%s\n", n++, d->name?d->name:"(null)", d->description?d->description:"(null)");
    }
    printf("TOTAL %d devices\n", n);
    if(freeall) freeall(devs);
    return 0;
}
