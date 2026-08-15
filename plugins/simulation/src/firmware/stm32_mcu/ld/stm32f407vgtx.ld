/* Linker script for STM32F407VGTx (Cortex-M4)
 * Flash: 1024KB @ 0x08000000
 * SRAM:  192KB  @ 0x20000000 (128KB + 64KB CCM)
 */
MEMORY
{
    FLASH  (rx) : ORIGIN = 0x08000000, LENGTH = 1024K
    SRAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
    CCM    (rwx) : ORIGIN = 0x10000000, LENGTH = 64K
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
