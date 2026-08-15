/* Startup code for STM32F407 (Cortex-M4)
 * Sets up stack, initializes data/bss, calls SystemInit then main
 */
.syntax unified
.cpu cortex-m4
.fpu softvfp
.thumb

.section .isr_vector, "a"
.global _estack
.global Reset_Handler

.word _estack                    /* Stack pointer */
.word Reset_Handler              /* Reset */
.word NMI_Handler                /* NMI */
.word HardFault_Handler          /* HardFault */
.word MemManage_Handler          /* MemManage */
.word BusFault_Handler           /* BusFault */
.word UsageFault_Handler         /* UsageFault */
.word 0
.word 0
.word 0
.word 0
.word SVC_Handler                /* SVCall */
.word DebugMon_Handler           /* Debug Monitor */
.word 0
.word PendSV_Handler             /* PendSV */
.word SysTick_Handler            /* SysTick */

/* Default handler */
.section .text.Default_Handler, "ax"
.weak NMI_Handler
.weak HardFault_Handler
.weak MemManage_Handler
.weak BusFault_Handler
.weak UsageFault_Handler
.weak SVC_Handler
.weak DebugMon_Handler
.weak PendSV_Handler
.weak SysTick_Handler

NMI_Handler:
HardFault_Handler:
MemManage_Handler:
BusFault_Handler:
UsageFault_Handler:
SVC_Handler:
DebugMon_Handler:
PendSV_Handler:
SysTick_Handler:
    b .  /* Infinite loop on fault */

/* Reset handler */
.section .text.Reset_Handler, "ax"
.global Reset_Handler
.type Reset_Handler, %function
Reset_Handler:
    /* Initialize data section */
    ldr r0, =_sdata
    ldr r1, =_edata
    ldr r2, =_etext
    cmp r0, r1
    beq 1f
0:  ldr r3, [r2], #4
    str r3, [r0], #4
    cmp r0, r1
    bne 0b

    /* Zero BSS section */
    ldr r0, =_sbss
    ldr r1, =_ebss
    mov r2, #0
    cmp r0, r1
    beq 2f
1:  /* Fill with zeros (word by word) */
    str r2, [r0], #4
    cmp r0, r1
    bne 1b

2:
    /* Call SystemInit */
    bl SystemInit
    /* Call main */
    bl main
    /* Should never return */
    b .
.size Reset_Handler, .-Reset_Handler
