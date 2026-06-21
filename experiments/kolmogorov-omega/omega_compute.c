#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define N 8
#define SPACE 1679616  /* 6^8 */
#define T_MAX 256
#define MASK 0xFF

typedef struct { uint8_t a; uint8_t b; } state_t;

/* 15 primitive operations */
static state_t op_inc(uint8_t a, uint8_t b) { return (state_t){(a+1)&MASK, b}; }
static state_t op_dec(uint8_t a, uint8_t b) { return (state_t){(a-1)&MASK, b}; }
static state_t op_swp(uint8_t a, uint8_t b) { return (state_t){b, a}; }
static state_t op_add(uint8_t a, uint8_t b) { return (state_t){(a+b)&MASK, b}; }
static state_t op_xor(uint8_t a, uint8_t b) { return (state_t){a^b, b}; }
static state_t op_neg(uint8_t a, uint8_t b) { return (state_t){(-a)&MASK, b}; }
static state_t op_mov(uint8_t a, uint8_t b) { return (state_t){a, a}; }
static state_t op_sub(uint8_t a, uint8_t b) { return (state_t){(a-b)&MASK, b}; }
static state_t op_and(uint8_t a, uint8_t b) { return (state_t){a&b, b}; }
static state_t op_or(uint8_t a, uint8_t b)  { return (state_t){a|b, b}; }
static state_t op_shr(uint8_t a, uint8_t b) { return (state_t){a>>1, b}; }
static state_t op_shl(uint8_t a, uint8_t b) { return (state_t){(a<<1)&MASK, b}; }
static state_t op_cpl(uint8_t a, uint8_t b) { return (state_t){(~a)&MASK, b}; }
static state_t op_nop(uint8_t a, uint8_t b) { return (state_t){a, b}; }

typedef state_t (*op_fn)(uint8_t, uint8_t);

static op_fn OP_TABLE[15] = {
    op_inc, op_dec, op_swp, op_add, op_xor,
    NULL,   /* 5 = JNZ, handled separately */
    op_neg, op_mov, op_sub, op_and, op_or,
    op_shr, op_shl, op_cpl, op_nop
};

int main(int argc, char **argv) {
    if (argc < 5) {
        fprintf(stderr, "Usage: omega_compute op1 op2 op3 op4\n");
        return 1;
    }
    int op_ids[5];
    op_ids[0] = 0;  /* opcode 0 = INC always */
    op_ids[1] = atoi(argv[1]);
    op_ids[2] = atoi(argv[2]);
    op_ids[3] = atoi(argv[3]);
    op_ids[4] = atoi(argv[4]);

    op_fn ops[5];
    for (int i = 0; i < 5; i++) {
        if (op_ids[i] < 0 || op_ids[i] > 14 || op_ids[i] == 5) {
            fprintf(stderr, "Invalid op_id %d\n", op_ids[i]);
            return 1;
        }
        ops[i] = OP_TABLE[op_ids[i]];
    }

    uint32_t halts = 0;
    for (uint32_t prog = 0; prog < SPACE; prog++) {
        uint8_t program[N];
        uint32_t tmp = prog;
        for (int i = 0; i < N; i++) { program[i] = tmp % 6; tmp /= 6; }

        uint8_t a = 0, b = 0;
        int pc = 0;
        int halted = 0;
        for (int step = 0; step < T_MAX; step++) {
            if (pc >= N) { halted = 1; break; }
            int opcode = program[pc];
            if (opcode == 5) {
                if (a != 0) pc = 0; else pc++;
            } else {
                state_t s = ops[opcode](a, b);
                a = s.a; b = s.b;
                pc++;
            }
        }
        if (halted) halts++;
    }
    printf("%u\n", halts);
    return 0;
}
