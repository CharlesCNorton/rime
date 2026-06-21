/* RIME-I test firmware: Fibonacci, factorial, GCD over UART. */

#include <stdint.h>

#define UART_TX_DATA  (*(volatile uint32_t *)0x20000000)
#define UART_TX_BUSY  (*(volatile uint32_t *)0x20000004)

static void uart_putc(char c) {
    while (UART_TX_BUSY & 1);
    UART_TX_DATA = c;
}

static void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}

static void uart_putnum(uint32_t n) {
    char buf[12];
    int i = 0;
    if (n == 0) { uart_putc('0'); return; }
    while (n > 0) { buf[i++] = '0' + (n % 10); n /= 10; }
    while (i > 0) uart_putc(buf[--i]);
}

static uint32_t fib(int n) {
    uint32_t a = 0, b = 1;
    for (int i = 0; i < n; i++) {
        uint32_t t = a + b;
        a = b;
        b = t;
    }
    return a;
}

static uint32_t factorial(int n) {
    uint32_t r = 1;
    for (int i = 2; i <= n; i++) r *= i;
    return r;
}

static uint32_t gcd(uint32_t a, uint32_t b) {
    while (b != 0) {
        uint32_t t = b;
        b = a % b;
        a = t;
    }
    return a;
}

void main(void) {
    uart_puts("RIME-I\n");

    uart_puts("FIB20=");
    uart_putnum(fib(20));
    uart_putc('\n');

    uart_puts("FACT10=");
    uart_putnum(factorial(10));
    uart_putc('\n');

    uart_puts("GCD(1071,462)=");
    uart_putnum(gcd(1071, 462));
    uart_putc('\n');

    uint32_t f = fib(20);
    uint32_t fact = factorial(10);
    uint32_t g = gcd(1071, 462);

    if (f == 6765 && fact == 3628800 && g == 21)
        uart_puts("PASS\n");
    else
        uart_puts("FAIL\n");
}
