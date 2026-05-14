/* ARM semihosting printf redirect for BiBa firmware.
 *
 * Overrides newlib's _write() syscall stub so that printf() / puts() output
 * is routed to the host debugger console via the SWD connection (BKPT 0xAB).
 *
 * Safety: the BKPT instruction causes a HardFault when no debugger is
 * attached.  The CoreDebug->DHCSR guard prevents that: the write is silently
 * discarded when running standalone without an ST-Link / GDB session.
 *
 * Usage:
 *   1. Build & Debug (F5) in VS Code / PlatformIO.
 *   2. Call printf() / puts() anywhere in the firmware.
 *   3. Output appears in the "Output" / "Debug Console" panel.
 *
 * NOTE: this file is compiled for all firmware envs (fw_common src_filter
 * picks up all of src/).  The overhead when running without a debugger is a
 * single register read per _write() call. */

#if !defined(BIBA_NATIVE_TEST)

#include "stm32f1xx_hal.h"
#include <stdint.h>

/* ARM semihosting operation codes (IHI0048B). */
#define SHF_SYS_WRITE  0x05u

/* Last HardFault PC — stored in .noinit so GDB firmware reload does NOT
 * zero it.  Read this value in Watch panel after the debugger halts. */
__attribute__((section(".noinit")))
volatile uint32_t g_last_hardfault_pc;
__attribute__((section(".noinit")))
volatile uint32_t g_last_hardfault_lr;

static int semihost_write(int fd, const char *buf, int len)
{
    /* Argument block expected by the SYS_WRITE semihosting call. */
    volatile uint32_t args[3] = {
        (uint32_t)fd,
        (uint32_t)(uintptr_t)buf,
        (uint32_t)len,
    };

    register uint32_t r0 asm("r0") = SHF_SYS_WRITE;
    register uint32_t r1 asm("r1") = (uint32_t)(uintptr_t)args;

    /* BKPT 0xAB is the ARM semihosting trap.  The host debugger intercepts
     * it and services the request; without a debugger this raises a fault. */
    asm volatile (
        "bkpt 0xAB"
        : "+r"(r0)
        : "r"(r1)
        : "memory"
    );

    /* SYS_WRITE returns the number of bytes NOT written (0 = full success). */
    return len - (int)r0;
}

/* Override the newlib weak _write stub.  Called by printf/puts/fwrite. */
int _write(int fd, char *ptr, int len)
{
    /* C_DEBUGEN bit: set by the debugger during an active debug session.
     * NOTE: some ST-Link firmwares leave C_DEBUGEN=1 after disconnect, so
     * this guard alone is not sufficient — see HardFault_Handler below. */
    if (!(CoreDebug->DHCSR & CoreDebug_DHCSR_C_DEBUGEN_Msk)) {
        return len;   /* no debugger attached — drop silently */
    }

    return semihost_write(fd, ptr, len);
}

/* HardFault recovery for semihosting BKPT 0xAB without a live debugger.
 *
 * When the firmware runs standalone after a debug session, ST-Link may leave
 * C_DEBUGEN=1 so our _write guard passes, but the BKPT 0xAB instruction
 * escalates to HardFault because no GDB is actually listening.
 *
 * This handler inspects the stacked PC.  If the faulting instruction is
 * BKPT 0xAB (encoding 0xBEAB) it sets R0 = -1 and advances PC past the
 * BKPT so execution resumes normally.  All other HardFaults loop forever
 * so they are still visible to the debugger. */
void semihosting_hardfault_recover(uint32_t *sp)
{
    uint32_t pc    = sp[6];          /* stacked PC */
    uint16_t instr = *(uint16_t *)pc;

    g_last_hardfault_pc = pc;
    g_last_hardfault_lr = sp[5];     /* stacked LR */

    if (instr == 0xBEABu) {          /* BKPT 0xAB — semihosting trap */
        sp[0] = (uint32_t)-1;        /* R0: return -1 (SYS_WRITE failure) */
        sp[6] = pc + 2u;             /* skip the 16-bit BKPT instruction  */
        return;                      /* return from exception — safe now   */
    }

    /* Real fault: trigger BKPT so an attached debugger halts here with
     * the full register context visible.  Without a debugger this will
     * escalate to another HardFault and loop — that is intentional. */
    __BKPT(0);
    while (1) { __NOP(); }
}

/* Overrides the weak Default_Handler alias for HardFault. */
__attribute__((naked))
void HardFault_Handler(void)
{
    /* Select MSP or PSP depending on which stack was active (bit 2 of LR). */
    __asm volatile (
        "tst   lr, #4          \n"
        "ite   eq              \n"
        "mrseq r0, msp         \n"
        "mrsne r0, psp         \n"
        "b     semihosting_hardfault_recover \n"
    );
}

#endif /* !BIBA_NATIVE_TEST */
