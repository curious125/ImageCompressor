#ifndef DELTA_RLE_H
#define DELTA_RLE_H

#ifdef __cplusplus
extern "C" {
#endif

unsigned int c_delta_rle_encode(const unsigned char* input, unsigned int len, unsigned char** output);
unsigned int c_delta_rle_decode(const unsigned char* input, unsigned int len, unsigned char** output);
void c_free_buffer(unsigned char* ptr);

#ifdef __cplusplus
}
#endif

#endif