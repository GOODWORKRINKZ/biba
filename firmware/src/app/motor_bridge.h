#ifndef BIBA_MOTOR_BRIDGE_H
#define BIBA_MOTOR_BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

/* Mirror the standalone arm-edge recovery: clear a possible BTS7960
 * thermal latch, then re-assert SSR power for the next run. */
void biba_motor_bridge_rearm(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_MOTOR_BRIDGE_H */