#ifndef BIBA_MODE_DISPATCHER_H
#define BIBA_MODE_DISPATCHER_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    BIBA_MODE_STANDALONE_E = 0,
    BIBA_MODE_COMPANION_E  = 1
} biba_mode_t;

/* One-time bring-up: HAL init, peripheral init, driver init. Called from
 * main() right after reset. */
void biba_mode_dispatcher_boot(void);

/* Never returns: runs the cooperative super-loop for the selected mode. */
void biba_mode_dispatcher_run_forever(void);

/* --- Per-mode entry points (called by the dispatcher) -------------------- */

void biba_mode_standalone_init(void);
void biba_mode_standalone_tick(void);

void biba_mode_companion_init(void);
void biba_mode_companion_tick(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_MODE_DISPATCHER_H */
