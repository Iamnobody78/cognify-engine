# BottleSumo Firmware Build System
# Dual MCU: STM32F407VGTx (main) + STM32F103C8Tx (aux)
# Toolchain: arm-none-eabi-gcc 10.3.1

# ---- Toolchain ----
CROSS = arm-none-eabi-
CC   = $(CROSS)gcc
AS   = $(CROSS)gcc -x assembler-with-cpp
OBJCOPY = $(CROSS)objcopy
SIZE    = $(CROSS)size

# ---- Directories ----
SRC_DIR   = src
BUILD_DIR = build
LD_DIR    = ld

# ---- Flags ----
ARCH_F407 = -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16
ARCH_F103 = -mcpu=cortex-m3 -mthumb

CWARN  = -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers
CDEFS  = -DSTM32F407xx
CFLAGS_F407 = $(ARCH_F407) $(CWARN) $(CDEFS) -Os -ffunction-sections -fdata-sections \
              -fno-common -fno-strict-aliasing -std=c11
CFLAGS_F103 = $(ARCH_F103) $(CWARN) -DSTM32F103xB -Os -ffunction-sections -fdata-sections \
              -fno-common -fno-strict-aliasing -std=c11

LDFLAGS_F407 = $(ARCH_F407) -T$(LD_DIR)/stm32f407vgtx.ld -Wl,--gc-sections \
               -nostartfiles -specs=nosys.specs -lc -lm -lnosys
LDFLAGS_F103 = $(ARCH_F103) -T$(LD_DIR)/stm32f103c8tx.ld -Wl,--gc-sections \
               -nostartfiles -specs=nosys.specs -lc -lm -lnosys

# ---- Source Files ----
# F407 (main)
SRC_F407 = $(SRC_DIR)/main_f407.c \
           $(SRC_DIR)/dqn_weights.c
ASM_F407 = $(SRC_DIR)/startup_f407.s

# F103 (aux)
SRC_F103 = $(SRC_DIR)/aux_f103.c
ASM_F103 = $(SRC_DIR)/startup_f103.s

# ---- Object Files ----
OBJ_F407 = $(patsubst $(SRC_DIR)/%.c, $(BUILD_DIR)/%_f407.o, $(SRC_F407)) \
           $(patsubst $(SRC_DIR)/%.s, $(BUILD_DIR)/%_f407.o, $(ASM_F407))
OBJ_F103 = $(patsubst $(SRC_DIR)/%.c, $(BUILD_DIR)/%_f103.o, $(SRC_F103)) \
           $(patsubst $(SRC_DIR)/%.s, $(BUILD_DIR)/%_f103.o, $(ASM_F103))

# ---- Targets ----
.PHONY: all clean

all: $(BUILD_DIR)/bottlesumo_main.elf $(BUILD_DIR)/bottlesumo_aux.elf

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# ---- F407 Main ----
$(BUILD_DIR)/bottlesumo_main.elf: $(OBJ_F407) | $(BUILD_DIR)
	$(CC) $(OBJ_F407) $(LDFLAGS_F407) -o $@
	$(SIZE) $@

$(BUILD_DIR)/%_f407.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS_F407) -c $< -o $@

$(BUILD_DIR)/%_f407.o: $(SRC_DIR)/%.s | $(BUILD_DIR)
	$(AS) $(ARCH_F407) -c $< -o $@

# ---- F103 Aux ----
$(BUILD_DIR)/bottlesumo_aux.elf: $(OBJ_F103) | $(BUILD_DIR)
	$(CC) $(OBJ_F103) $(LDFLAGS_F103) -o $@
	$(SIZE) $@

$(BUILD_DIR)/%_f103.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS_F103) -c $< -o $@

$(BUILD_DIR)/%_f103.o: $(SRC_DIR)/%.s | $(BUILD_DIR)
	$(AS) $(ARCH_F103) -c $< -o $@

# ---- Clean ----
clean:
	rm -rf $(BUILD_DIR)

# ---- Renode sim build ----
renode: CFLAGS_F407 += -DRENODE_SIM
renode: CFLAGS_F103 += -DRENODE_SIM
renode: all

# ---- Debug ----
dump-f407: $(BUILD_DIR)/bottlesumo_main.elf
	$(CROSS)objdump -d $< | head -50

dump-f103: $(BUILD_DIR)/bottlesumo_aux.elf
	$(CROSS)objdump -d $< | head -50
