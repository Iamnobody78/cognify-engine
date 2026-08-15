/* Minimal STM32F4xx register definitions for BottleSumo simulation
 * Cortex-M4 with FPU, F407 @ 168MHz
 * Only defines registers actually used by main_f407.c
 */
#ifndef STM32F4XX_REG_H
#define STM32F4XX_REG_H

#include <stdint.h>

/* ---- Memory Map ---- */
#define PERIPH_BASE        0x40000000U
#define APB1PERIPH_BASE    (PERIPH_BASE)
#define APB2PERIPH_BASE    (PERIPH_BASE + 0x00010000U)
#define AHB1PERIPH_BASE    (PERIPH_BASE + 0x00020000U)

/* AHB1 - GPIO */
#define GPIOA_BASE         (AHB1PERIPH_BASE + 0x0000U)
#define GPIOB_BASE         (AHB1PERIPH_BASE + 0x0400U)
#define GPIOC_BASE         (AHB1PERIPH_BASE + 0x0800U)
#define RCC_BASE           (AHB1PERIPH_BASE + 0x3800U)

/* APB1 - SPI2, I2C1, USART3, IWDG, TIM2/3/4/5 */
#define TIM2_BASE          (APB1PERIPH_BASE + 0x0000U)
#define TIM3_BASE          (APB1PERIPH_BASE + 0x0400U)
#define TIM4_BASE          (APB1PERIPH_BASE + 0x0800U)
#define TIM5_BASE          (APB1PERIPH_BASE + 0x0C00U)
#define SPI2_BASE          (APB1PERIPH_BASE + 0x3800U)
#define USART3_BASE        (APB1PERIPH_BASE + 0x4800U)
#define I2C1_BASE          (APB1PERIPH_BASE + 0x5400U)
#define IWDG_BASE          (APB1PERIPH_BASE + 0x3000U)

/* APB2 - USART1, SPI1, TIM1 */
#define TIM1_BASE          (APB2PERIPH_BASE + 0x0000U)
#define USART1_BASE        (APB2PERIPH_BASE + 0x1000U)
#define SPI1_BASE          (APB2PERIPH_BASE + 0x3000U)
#define SYSCFG_BASE        (APB2PERIPH_BASE + 0x3800U)

/* ---- GPIO Register Structures ---- */
typedef struct {
    volatile uint32_t MODER;    /* 0x00 - Mode */
    volatile uint32_t OTYPER;   /* 0x04 - Output type */
    volatile uint32_t OSPEEDR;  /* 0x08 - Speed */
    volatile uint32_t PUPDR;    /* 0x0C - Pull-up/down */
    volatile uint32_t IDR;      /* 0x10 - Input data */
    volatile uint32_t ODR;      /* 0x14 - Output data */
    volatile uint32_t BSRR;     /* 0x18 - Bit set/reset */
    volatile uint32_t LCKR;     /* 0x1C - Lock */
    volatile uint32_t AFRL;     /* 0x20 - Alt function low */
    volatile uint32_t AFRH;     /* 0x24 - Alt function high */
} GPIO_TypeDef;

#define GPIOA  ((GPIO_TypeDef *)GPIOA_BASE)
#define GPIOB  ((GPIO_TypeDef *)GPIOB_BASE)
#define GPIOC  ((GPIO_TypeDef *)GPIOC_BASE)

/* ---- RCC Register Structure ---- */
typedef struct {
    volatile uint32_t CR;        /* 0x00 */
    volatile uint32_t PLLCFGR;   /* 0x04 */
    volatile uint32_t CFGR;      /* 0x08 */
    volatile uint32_t CIR;       /* 0x0C */
    volatile uint32_t AHB1RSTR;  /* 0x10 */
    volatile uint32_t AHB2RSTR;  /* 0x14 */
    volatile uint32_t AHB3RSTR;  /* 0x18 */
    uint32_t RESERVED0;
    volatile uint32_t APB1RSTR;  /* 0x20 */
    volatile uint32_t APB2RSTR;  /* 0x24 */
    uint32_t RESERVED1[2];
    volatile uint32_t AHB1ENR;   /* 0x30 */
    volatile uint32_t AHB2ENR;   /* 0x34 */
    volatile uint32_t AHB3ENR;   /* 0x38 */
    uint32_t RESERVED2;
    volatile uint32_t APB1ENR;   /* 0x40 */
    volatile uint32_t APB2ENR;   /* 0x44 */
} RCC_TypeDef;

#define RCC   ((RCC_TypeDef *)RCC_BASE)

/* RCC bits */
#define RCC_CR_HSERDY       (1U << 17)
#define RCC_CR_HSEON        (1U << 16)
#define RCC_CR_HSIRDY       (1U << 1)
#define RCC_CR_HSION        (1U << 0)
#define RCC_CR_PLLRDY       (1U << 25)
#define RCC_CR_PLLON        (1U << 24)

#define RCC_AHB1ENR_GPIOA   (1U << 0)
#define RCC_AHB1ENR_GPIOB   (1U << 1)
#define RCC_AHB1ENR_GPIOC   (1U << 2)
#define RCC_APB1ENR_TIM2    (1U << 0)
#define RCC_APB1ENR_TIM3    (1U << 1)
#define RCC_APB1ENR_TIM4    (1U << 2)
#define RCC_APB1ENR_TIM5    (1U << 3)
#define RCC_APB1ENR_SPI2    (1U << 14)
#define RCC_APB1ENR_USART3  (1U << 18)
#define RCC_APB1ENR_I2C1    (1U << 21)
#define RCC_APB1ENR_IWDG    (1U << 29)
#define RCC_APB2ENR_TIM1    (1U << 0)
#define RCC_APB2ENR_USART1  (1U << 4)
#define RCC_APB2ENR_SPI1    (1U << 12)
#define RCC_APB2ENR_SYSCFG  (1U << 14)

/* ---- SPI Register Structure ---- */
typedef struct {
    volatile uint32_t CR1;       /* 0x00 */
    volatile uint32_t CR2;       /* 0x04 */
    volatile uint32_t SR;        /* 0x08 */
    volatile uint32_t DR;        /* 0x0C */
    volatile uint32_t CRCPR;     /* 0x10 */
    volatile uint32_t RXCRCR;    /* 0x14 */
    volatile uint32_t TXCRCR;    /* 0x18 */
} SPI_TypeDef;

#define SPI2  ((SPI_TypeDef *)SPI2_BASE)

/* SPI bits */
#define SPI_CR1_CPHA       (1U << 0)
#define SPI_CR1_CPOL       (1U << 1)
#define SPI_CR1_MSTR       (1U << 2)
#define SPI_CR1_BR_SHIFT   3
#define SPI_CR1_SPE        (1U << 6)
#define SPI_CR1_LSBFIRST   (1U << 7)
#define SPI_CR1_SSI        (1U << 8)
#define SPI_CR1_SSM        (1U << 9)
#define SPI_CR1_DFF        (1U << 11)  /* 16-bit frame */
#define SPI_CR1_BIDIMODE   (1U << 15)
#define SPI_CR1_BIDIOE     (1U << 14)
#define SPI_SR_RXNE        (1U << 0)
#define SPI_SR_TXE         (1U << 1)
#define SPI_SR_BSY         (1U << 7)

/* ---- I2C Register Structure (simplified) ---- */
typedef struct {
    volatile uint32_t CR1;       /* 0x00 */
    volatile uint32_t CR2;       /* 0x04 */
    volatile uint32_t OAR1;      /* 0x08 */
    volatile uint32_t OAR2;      /* 0x0C */
    volatile uint32_t DR;        /* 0x10 */
    volatile uint32_t SR1;       /* 0x14 */
    volatile uint32_t SR2;       /* 0x18 */
    volatile uint32_t CCR;       /* 0x1C */
    volatile uint32_t TRISE;     /* 0x20 */
    volatile uint32_t FLTR;      /* 0x24 */
} I2C_TypeDef;

#define I2C1  ((I2C_TypeDef *)I2C1_BASE)

/* I2C bits */
#define I2C_CR1_PE         (1U << 0)
#define I2C_CR1_START      (1U << 8)
#define I2C_CR1_STOP       (1U << 9)
#define I2C_CR1_ACK        (1U << 10)
#define I2C_SR1_SB         (1U << 0)
#define I2C_SR1_ADDR       (1U << 1)
#define I2C_SR1_BTF        (1U << 2)
#define I2C_SR1_RXNE       (1U << 6)
#define I2C_SR1_TXE        (1U << 7)

/* ---- USART Register Structure ---- */
typedef struct {
    volatile uint32_t SR;        /* 0x00 */
    volatile uint32_t DR;        /* 0x04 */
    volatile uint32_t BRR;       /* 0x08 */
    volatile uint32_t CR1;       /* 0x0C */
    volatile uint32_t CR2;       /* 0x10 */
    volatile uint32_t CR3;       /* 0x14 */
    volatile uint32_t GTPR;      /* 0x18 */
} USART_TypeDef;

#define USART3  ((USART_TypeDef *)USART3_BASE)

#define USART_SR_TXE      (1U << 7)
#define USART_SR_RXNE     (1U << 5)
#define USART_CR1_UE      (1U << 13)
#define USART_CR1_TE      (1U << 3)
#define USART_CR1_RE      (1U << 2)

/* ---- IWDG Register Structure ---- */
typedef struct {
    volatile uint32_t KR;        /* 0x00 */
    volatile uint32_t PR;        /* 0x04 */
    volatile uint32_t RLR;       /* 0x08 */
    volatile uint32_t SR;        /* 0x0C */
} IWDG_TypeDef;

#define IWDG  ((IWDG_TypeDef *)IWDG_BASE)

#define IWDG_KR_KEY_ENABLE  0xCCCCU
#define IWDG_KR_KEY_REFRESH 0xAAAAU
#define IWDG_KR_KEY_ACCESS  0x5555U

/* ---- SysTick ---- */
typedef struct {
    volatile uint32_t CTRL;      /* 0x00 */
    volatile uint32_t LOAD;      /* 0x04 */
    volatile uint32_t VAL;       /* 0x08 */
    volatile uint32_t CALIB;     /* 0x0C */
} SysTick_TypeDef;

#define SysTick  ((SysTick_TypeDef *)0xE000E010U)

#define SysTick_CTRL_ENABLE    (1U << 0)
#define SysTick_CTRL_TICKINT   (1U << 1)
#define SysTick_CTRL_CLKSOURCE (1U << 2)
#define SysTick_CTRL_COUNTFLAG (1U << 16)

/* ---- NVIC ---- */
#define NVIC_ISER0  (*(volatile uint32_t *)0xE000E100U)
#define NVIC_ICER0  (*(volatile uint32_t *)0xE000E180U)
#define NVIC_ISPR0  (*(volatile uint32_t *)0xE000E200U)
#define NVIC_ICPR0  (*(volatile uint32_t *)0xE000E280U)
#define NVIC_IPR(x) (*(volatile uint8_t *)(0xE000E400U + (x)))

/* ---- SCB ---- */
#define SCB_CPACR   (*(volatile uint32_t *)0xE000ED88U)
#define SCB_CPACR_FPU_ENABLE  (0xFU << 20)

/* ---- FLASH ---- */
#define FLASH_ACR    (*(volatile uint32_t *)0x40023C00U)
#define FLASH_ACR_LATENCY_5WS  (5U << 0)
#define FLASH_ACR_PRFTEN       (1U << 8)
#define FLASH_ACR_ICEN         (1U << 9)
#define FLASH_ACR_DCEN         (1U << 10)

/* ---- Helper macros ---- */
static inline void __WFI(void) { __asm__ volatile("wfi"); }
static inline void __DMB(void) { __asm__ volatile("dmb"); }
static inline void __DSB(void) { __asm__ volatile("dsb"); }

#endif /* STM32F4XX_REG_H */
