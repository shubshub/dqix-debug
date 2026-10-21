set pagination off
set confirm off
set architecture armv5te
set remote noack-packet off
target remote localhost:3333
echo \n=== stopped on connect ===\n
info line *$pc
bt 6
echo \n=== breakpoint on a per-frame function, then continue ===\n
tbreak func_020c9bf0
continue
bt 6
echo \n=== up into the caller: source + locals ===\n
up
list
info locals
echo \n=== a function with arguments ===\n
frame 2
info args
detach
