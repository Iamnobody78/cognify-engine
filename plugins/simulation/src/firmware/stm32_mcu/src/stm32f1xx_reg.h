/* Minimal STM32F103xx register definitions for BottleSumo simulation
 * Cortex-M3, F103 @ 72MHz
 * Only defines registers actually used by aux_f103.c
 */
#ifndef STM32F1XX_REG_H
#define STM32F1XX_REG_H

#include <stdint.h>

/* ---- Memory Map ---- */
#define PERIPH_BASE        0x40000000U
#define APB1PERIPH_BASE    PERIPH_BASE
#define APB2PERIPH_BASE    (PERIPH_BASE + 0x00010000U)
#define AHBPERIPH_BASE     (PERIPH_BASE + 0x00018000U)

/* AHB */
#define RCC_BASE           (AHBPERIPH_BASE + 0x00009000U)

/* APB1 - TIM2/3/4, SPI2, I2C1/2 */
#define TIM2_BASE          (APB1PERIPH_BASE + 0x0000U)
#define TIM3_BASE          (APB1PERIPH_BASE + 0x0400U)
#define TIM4_BASE          (APB1PERIPH_BASE + 0x0800U)
#define I2C2_BASE          (APB1PERIPH_BASE + 0x5800U)

/* APB2 - GPIO, TIM1, SPI1, ADC1, USART1 */
#define AFIO_BASE          (APB2PERIPH_BASE + 0x0000U)
#define GPIOA_BASE         (APB2PERIPH_BASE + 0x0800U)
#define GPIOB_BASE         (APB2PERIPH_BASE + 0x0C00U)
#define GPIOC_BASE         (APB2PERIPH_BASE + 0x1000U)
#define ADC1_BASE          (APB2PERIPH_BASE + 0x2400U)
#define TIM1_BASE          (APB2PERIPH_BASE + 0x2C00U)
#define SPI1_BASE          (APB2PERIPH_BASE + 0x3000U)

/* ---- GPIO Register Structure ---- */
typedef struct {
    volatile uint32_t CRL;       /* 0x00 - Config low (pins 0-7) */
    volatile uint32_t CRH;       /* 0x04 - Config high (pins 8-15) */
    volatile uint32_t IDR;       /* 0x08 - Input data */
    volatile uint32_t ODR;       /* 0x0C - Output data */
    volatile uint32_t BSRR;      /* 0x10 - Bit set/reset */
    volatile uint32_t BRR;       /* 0x14 - Bit reset */
    volatile uint32_t LCKR;      /* 0x18 - Lock */
} GPIO_TypeDef;

#define GPIOA  ((GPIO_TypeDef *)GPIOA_BASE)
#define GPIOB  ((GPIO_TypeDef *)GPIOB_BASE)
#define GPIOC  ((GPIO_TypeDef *)GPIOC_BASE)

/* ---- RCC Register Structure ---- */
typedef struct {
    volatile uint32_t CR;
    volatile uint32_t CFGR;
    volatile uint32_t CIR;
    volatile uint32_t APB2RSTR;
    volatile uint32_t APB1RSTR;
    volatile uint32_t AHBENR;
    volatile uint32_t APB2ENR;
    volatile uint32_t APB1ENR;
} RCC_TypeDef;

#define RCC   ((RCC_TypeDef *)RCC_BASE)

/* RCC bits */
#define RCC_CR_HSION       (1U << 0)
#define RCC_CR_HSIRDY      (1U << 1)
#define RCC_CR_HSEON       (1U << 16)
#define RCC_CR_HSERDY      (1U << 17)
#define RCC_CR_PLLON       (1U << 24)
#define RCC_CR_PLLRDY      (1U << 25)

#define RCC_AHBENR_DMA1    (1U << 0)
#define RCC_APB1ENR_TIM2   (1U << 0)
#define RCC_APB1ENR_TIM3   (1U << 1)
#define RCC_APB1ENR_TIM4   (1U << 2)
#define RCC_APB1ENR_I2C2   (1U << 22)
#define RCC_APB2ENR_AFIO   (1U << 0)
#define RCC_APB2ENR_IOPA   (1U << 2)
#define RCC_APB2ENR_IOPB   (1U << 3)
#define RCC_APB2ENR_IOPC   (1U << 4)
#define RCC_APB2ENR_ADC1   (1U << 9)
#define RCC_APB2ENR_TIM1   (1U << 11)
#define RCC_APB2ENR_SPI1   (1U << 12)

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

#define SPI1  ((SPI_TypeDef *)SPI1_BASE)

#define SPI_CR1_CPHA       (1U << 0)
#define SPI_CR1_CPOL       (1U << 1)
#define SPI_CR1_MSTR       (1U << 2)
#define SPI_CR1_BR_SHIFT   3
#define SPI_CR1_SPE        (1U << 6)
#define SPI_CR1_SSI        (1U << 8)
#define SPI_CR1_SSM        (1U << 9)
#define SPI_CR1_LSBFIRST   (1U << 7)
#define SPI_CR1_DFF        (1U << 11)  /* F103: 16-bit = 1? No, F103 SPI_CR1 is different but we use compatible bits */
#define SPI_SR_RXNE        (1U << 0)
#define SPI_SR_TXE         (1U << 1)
#define SPI_SR_BSY         (1U << 7)

/* ---- I2C Register Structure ---- */
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
} I2C_TypeDef;

#define I2C2  ((I2C_TypeDef *)I2C2_BASE)

#define I2C_CR1_PE         (1U << 0)
#define I2C_CR1_START      (1U << 8)
#define I2C_CR1_STOP       (1U << 9)
#define I2C_CR1_ACK        (1U << 10)
#define I2C_SR1_SB         (1U << 0)
#define I2C_SR1_ADDR       (1U << 1)
#define I2C_SR1_BTF        (1U << 2)
#define I2C_SR1_RXNE       (1U << 6)
#define I2C_SR1_TXE        (1U << 7)

/* ---- TIM Register Structure ---- */
typedef struct {
    volatile uint32_t CR1;       /* 0x00 */
    volatile uint32_t CR2;       /* 0x04 */
    volatile uint32_t SMCR;      /* 0x08 */
    volatile uint32_t DIER;      /* 0x0C */
    volatile uint32_t SR;        /* 0x10 */
    volatile uint32_t EGR;       /* 0x14 */
    volatile uint32_t CCMR1;     /* 0x18 */
    volatile uint32_t CCMR2;     /* 0x1C */
    volatile uint32_t CCER;      /* 0x20 */
    volatile uint32_t CNT;       /* 0x24 */
    volatile uint32_t PSC;       /* 0x28 */
    volatile uint32_t ARR;       /* 0x2C */
    volatile uint32_t RCR;       /* 0x30 */
    volatile uint32_t CCR1;      /* 0x34 */
    volatile uint32_t CCR2;      /* 0x38 */
    volatile uint32_t CCR3;      /* 0x3C */
    volatile uint32_t CCR4;      /* 0x40 */
    volatile uint32_t BDTR;      /* 0x44 (TIM1 only) */
    volatile uint32_t DCR;       /* 0x48 */
    volatile uint32_t DMAR;      /* 0x4C */
} TIM_TypeDef;

#define TIM1  ((TIM_TypeDef *)TIM1_BASE)
#define TIM2  ((TIM_TypeDef *)TIM2_BASE)
#define TIM4  ((TIM_TypeDef *)TIM4_BASE)

/* TIM bits */
#define TIM_CR1_CEN       (1U << 0)
#define TIM_CR1_ARPE      (1U << 7)
#define TIM_CCER_CC1E     (1U << 0)
#define TIM_CCER_CC2E     (1U << 4)
#define TIM_CCER_CC1P     (1U << 1)
#define TIM_CCER_CC2P     (1U << 5)
#define TIM_CCMR1_OC1M_PWM1 (6U << 4)
#define TIM_CCMR1_OC1PE   (1U << 3)
#define TIM_CCMR1_OC2M_PWM1 (6U << 12)
#define TIM_CCMR1_OC2PE   (1U << 11)
#define TIM_EGR_UG        (1U << 0)
#define TIM_BDTR_MOE      (1U << 15)
#define TIM_SMCR_SMS_ENC  (3U << 0)  /* Encoder mode 3 (both edges) */

/* ---- ADC Register Structure ---- */
typedef struct {
    volatile uint32_t SR;        /* 0x00 */
    volatile uint32_t CR1;       /* 0x04 */
    volatile uint32_t CR2;       /* 0x08 */
    volatile uint32_t SMPR1;     /* 0x0C */
    volatile uint32_t SMPR2;     /* 0x10 */
    volatile uint32_t JOFR1;     /* 0x14 */
    volatile uint32_t JOFR2;     /* 0x18 */
    volatile uint32_t JOFR3;     /* 0x1C */
    volatile uint32_t JOFR4;     /* 0x20 */
    volatile uint32_t HTR;       /* 0x24 */
    volatile uint32_t LTR;       /* 0x28 */
    volatile uint32_t SQR1;      /* 0x2C */
    volatile uint32_t SQR2;      /* 0x30 */
    volatile uint32_t SQR3;      /* 0x34 */
    volatile uint32_t JSQR;      /* 0x38 */
    volatile uint32_t JDR1;      /* 0x3C */
    volatile uint32_t JDR2;      /* 0x40 */
    volatile uint32_t JDR3;      /* 0x44 */
    volatile uint32_t JDR4;      /* 0x48 */
    volatile uint32_t DR;        /* 0x4C */
} ADC_TypeDef;

#define ADC1  ((ADC_TypeDef *)ADC1_BASE)

#define ADC_CR2_ADON      (1U << 0)
#define ADC_CR2_CONT      (1U << 1)
#define ADC_CR2_SWSTART   (1U << 22)
#define ADC_SR_EOC        (1U << 1)

/* ---- IWDG Register Structure ---- */
typedef struct {
    volatile uint32_t KR;        /* 0x00 */
    volatile uint32_t PR;        /* 0x04 */
    volatile uint32_t RLR;       /* 0x08 */
    volatile uint32_t SR;        /* 0x0C */
} IWDG_TypeDef;

#define IWDG  ((IWDG_TypeDef *)0x40003000U)

#define IWDG_KR_KEY_ENABLE  0xCCCCU
#define IWDG_KR_KEY_REFRESH 0xAAAAU
#define IWDG_KR_KEY_ACCESS  0x5555U

/* ---- NVIC ---- */
typedef struct {
    volatile uint32_t ISER[8];   /* 0x000 - Interrupt Set Enable */
    volatile uint32_t RES0[24];
    volatile uint32_t ICER[8];   /* 0x080 - Interrupt Clear Enable */
    volatile uint32_t RES1[24];
    volatile uint32_t ISPR[8];   /* 0x100 - Interrupt Set Pending */
    volatile uint32_t RES2[24];
    volatile uint32_t ICPR[8];   /* 0x180 - Interrupt Clear Pending */
    volatile uint32_t RES3[24];
    volatile uint32_t IABR[8];   /* 0x200 - Interrupt Active Bit */
    volatile uint32_t RES4[56];
    volatile uint32_t IPR[60];   /* 0x300 - Interrupt Priority */
} NVIC_TypeDef;

#define NVIC  ((NVIC_TypeDef *)0xE000E100U)

/* ---- SysTick ---- */
typedef struct {
    volatile uint32_t CTRL;
    volatile uint32_t LOAD;
    volatile uint32_t VAL;
    volatile uint32_t CALIB;
} SysTick_TypeDef;

#define SysTick  ((SysTick_TypeDef *)0xE000E010U)

#define SysTick_CTRL_ENABLE    (1U << 0)
#define SysTick_CTRL_TICKINT   (1U << 1)
#define SysTick_CTRL_CLKSOURCE (1U << 2)
#define SysTick_CTRL_COUNTFLAG (1U << 16)

/* ---- Helper macros ---- */
static inline void __WFI(void) { __asm__ volatile("wfi"); }
static inline void __DMB(void) { __asm__ volatile("dmb"); }

#endif /* STM32F1XX_REG_H */
