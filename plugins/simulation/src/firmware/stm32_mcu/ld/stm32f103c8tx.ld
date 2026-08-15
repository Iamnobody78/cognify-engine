/* Linker script for STM32F103C8Tx (Cortex-M3)
 * Flash: 64KB @ 0x08000000
 * SRAM:  20KB @ 0x20000000
 */
MEMORY
{
    FLASH  (rx) : ORIGIN = 0x08000000, LENGTH = 64K
    SRAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}

_estack = ORIGIN(SRAM) + LENGTH(SRAM);

SECTIONS
{
    .isr_vector :
    {
        KEEP(*(.isr_vector))
        . = ALIGN(4);
    } > FLASH

    .text :
    {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
        _etext = .;
    } > FLASH

    .data : AT(_etext)
    {
        _sdata = .;
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > SRAM

    .bss :
    {
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > SRAM
}
