CROSS   = riscv32-unknown-elf-
CC      = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy

CFLAGS  = -march=rv32i -mabi=ilp32 -Os -Wall -ffreestanding -nostdlib
LDFLAGS = -T link.ld -nostartfiles -Wl,--gc-sections

SRCS    = start.S main.c
TARGET  = firmware

all: $(TARGET).bin $(TARGET).hex

$(TARGET).elf: $(SRCS) link.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(SRCS)

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O verilog $< $@

clean:
	rm -f $(TARGET).elf $(TARGET).bin $(TARGET).hex

.PHONY: all clean
