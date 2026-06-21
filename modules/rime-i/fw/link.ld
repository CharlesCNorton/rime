/* RIME-I linker script: 4 KB unified BRAM at 0x00000000 */

MEMORY
{
    RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 4K
}

SECTIONS
{
    .text :
    {
        *(.text.start)
        *(.text .text.*)
    } > RAM

    .rodata :
    {
        *(.rodata .rodata.*)
    } > RAM

    .data :
    {
        *(.data .data.*)
    } > RAM

    .bss :
    {
        __bss_start = .;
        *(.bss .bss.*)
        *(COMMON)
        __bss_end = .;
    } > RAM

    _stack_top = ORIGIN(RAM) + LENGTH(RAM);
}
