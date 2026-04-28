# Motor-audio command for the BiBa motor synth (composition C).
#
# kind selects the playback mode on the target firmware/runtime:
#   0 = silence, 1 = beacon, 2 = melody by name, 3 = raw tone.
# name is the melody/voice identifier when kind == 2.
# frequency_hz / duration_ms are used when kind == 3 (raw tone).
std_msgs/Header header
uint8 kind
string name
float32 frequency_hz
uint32 duration_ms
