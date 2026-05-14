#include "failsafe.h"

#include <string.h>

void biba_failsafe_init(biba_failsafe_t *fs, uint32_t timeout_ms)
{
    if (fs == NULL) return;
    fs->timeout_ms = timeout_ms;
    fs->last_ok_ms = 0;
    fs->primed = false;
    fs->active = true;  /* default-active until we see at least one frame */
}

void biba_failsafe_mark_fresh(biba_failsafe_t *fs, uint32_t now_ms)
{
    if (fs == NULL) return;
    fs->last_ok_ms = now_ms;
    fs->primed = true;
    fs->active = false;
}

bool biba_failsafe_tick(biba_failsafe_t *fs, uint32_t now_ms)
{
    if (fs == NULL) return true;
    if (!fs->primed) {
        fs->active = true;
        return true;
    }
    if (fs->timeout_ms == 0) {
        fs->active = false;
        return false;
    }
    uint32_t delta = now_ms - fs->last_ok_ms;
    fs->active = (delta >= fs->timeout_ms);
    return fs->active;
}

bool biba_failsafe_is_active(const biba_failsafe_t *fs)
{
    return (fs != NULL) ? fs->active : true;
}
