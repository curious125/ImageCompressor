#include "delta_rle.h"

#if defined(_WIN64) || defined(__x86_64__) || defined(__aarch64__)
typedef unsigned long long c_size_t;
#else
typedef unsigned int c_size_t;
#endif

#ifdef __cplusplus
extern "C" {
#endif
void* malloc(c_size_t size);
void free(void* ptr);
#ifdef __cplusplus
}
#endif

unsigned int c_delta_rle_encode(const unsigned char* input, unsigned int len, unsigned char** output) {
    unsigned char* delta;
    unsigned char* rle;
    unsigned int i;
    unsigned int out_idx;
    unsigned int run;
    unsigned int lit_start;
    unsigned int lit_len;
    unsigned int k;

    if (!input || !output || len == 0) return 0;

    delta = (unsigned char*)malloc((c_size_t)len);
    if (!delta) return 0;

    delta[0] = input[0];
    for (i = 1; i < len; i++) {
        delta[i] = (unsigned char)(input[i] - input[i - 1]);
    }

    /* PackBits worst-case is len + (len / 128) + 2 bytes */
    rle = (unsigned char*)malloc((c_size_t)len + ((c_size_t)len / 64) + 16);
    if (!rle) {
        free(delta);
        return 0;
    }

    out_idx = 0;
    i = 0;
    while (i < len) {
        run = 1;
        while ((i + run) < len && delta[i + run] == delta[i] && run < 128) {
            run++;
        }

        if (run >= 2) {
            /* High bit 1 = repeat run of (run) identical bytes */
            rle[out_idx++] = (unsigned char)(0x80 | (run - 1));
            rle[out_idx++] = delta[i];
            i += run;
        } else {
            /* High bit 0 = literal run of (lit_len) distinct bytes */
            lit_start = i;
            lit_len = 1;
            i++;
            while (i < len && lit_len < 128) {
                if ((i + 2) < len && delta[i] == delta[i + 1] && delta[i] == delta[i + 2]) {
                    break;
                }
                lit_len++;
                i++;
            }
            rle[out_idx++] = (unsigned char)(lit_len - 1);
            for (k = 0; k < lit_len; k++) {
                rle[out_idx++] = delta[lit_start + k];
            }
        }
    }

    free(delta);
    *output = rle;
    return out_idx;
}

unsigned int c_delta_rle_decode(const unsigned char* input, unsigned int len, unsigned char** output) {
    unsigned int total_pixels;
    unsigned int idx;
    unsigned int pos;
    unsigned int run;
    unsigned int k;
    unsigned int i;
    unsigned char ctrl;
    unsigned char val;
    unsigned char* reconstructed;

    if (!input || !output || len == 0) return 0;

    /* Pass 1: compute exact decoded byte count */
    total_pixels = 0;
    idx = 0;
    while (idx < len) {
        ctrl = input[idx++];
        run = (unsigned int)(ctrl & 0x7F) + 1;
        if (ctrl & 0x80) {
            if (idx >= len) return 0;
            idx++;
        } else {
            if (idx + run > len) return 0;
            idx += run;
        }
        total_pixels += run;
    }

    if (total_pixels == 0) return 0;

    reconstructed = (unsigned char*)malloc((c_size_t)total_pixels);
    if (!reconstructed) return 0;

    /* Pass 2: unpack repeat & literal runs */
    idx = 0;
    pos = 0;
    while (idx < len) {
        ctrl = input[idx++];
        run = (unsigned int)(ctrl & 0x7F) + 1;
        if (ctrl & 0x80) {
            val = input[idx++];
            for (k = 0; k < run; k++) {
                reconstructed[pos++] = val;
            }
        } else {
            for (k = 0; k < run; k++) {
                reconstructed[pos++] = input[idx++];
            }
        }
    }

    /* Pass 3: reverse delta encoding */
    for (i = 1; i < total_pixels; i++) {
        reconstructed[i] = (unsigned char)(reconstructed[i] + reconstructed[i - 1]);
    }

    *output = reconstructed;
    return total_pixels;
}

void c_free_buffer(unsigned char* ptr) {
    free(ptr);
}