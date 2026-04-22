#include "modes/mode_dispatcher.h"

int main(void)
{
    biba_mode_dispatcher_boot();
    biba_mode_dispatcher_run_forever();
    return 0;
}
