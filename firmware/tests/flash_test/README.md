# flash_test

Minimal JEDEC probe: reads the SPI flash JEDEC ID on power-up via USRMCLK,
streams the 3-byte result over UART as hex + newline. Send any byte over
UART to trigger another read.

Used as a standalone board-level validation fixture — confirms that the
FPGA can talk to the W25Q128 flash through the fabric SPI path before
trusting the full resident service.
