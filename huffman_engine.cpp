#include "delta_rle.h"

#if defined(_WIN64) || defined(__x86_64__) || defined(__aarch64__)
typedef unsigned long long cpp_size_t;
#else
typedef unsigned int cpp_size_t;
#endif

extern "C" {
    void* malloc(cpp_size_t size);
    void* realloc(void* ptr, cpp_size_t size);
    void free(void* ptr);
}

#ifdef _WIN32
  #define EXPORT __declspec(dllexport)
#else
  #define EXPORT
#endif

struct HuffmanNode {
    unsigned char symbol;
    unsigned int freq;
    int min_sym;
    HuffmanNode* left;
    HuffmanNode* right;
};

static HuffmanNode* createLeaf(unsigned char s, unsigned int f) {
    HuffmanNode* node = (HuffmanNode*)malloc(sizeof(HuffmanNode));
    if (!node) return 0;
    node->symbol = s;
    node->freq = f;
    node->min_sym = (int)s;
    node->left = 0;
    node->right = 0;
    return node;
}

static HuffmanNode* createInternal(HuffmanNode* l, HuffmanNode* r) {
    HuffmanNode* node = (HuffmanNode*)malloc(sizeof(HuffmanNode));
    if (!node) return 0;
    node->symbol = 0;
    node->freq = l->freq + r->freq;
    node->min_sym = (l->min_sym < r->min_sym) ? l->min_sym : r->min_sym;
    node->left = l;
    node->right = r;
    return node;
}

static void freeTree(HuffmanNode* node) {
    if (!node) return;
    freeTree(node->left);
    freeTree(node->right);
    free(node);
}

static bool nodeLess(const HuffmanNode* a, const HuffmanNode* b) {
    if (a->freq != b->freq) return a->freq < b->freq;
    return a->min_sym < b->min_sym;
}

class MinHeap {
private:
    HuffmanNode* data[512];
    int count;

public:
    MinHeap() : count(0) {}

    int size() const { return count; }

    void push(HuffmanNode* node) {
        int i = count++;
        data[i] = node;
        while (i > 0) {
            int parent = (i - 1) / 2;
            if (nodeLess(data[i], data[parent])) {
                HuffmanNode* tmp = data[i];
                data[i] = data[parent];
                data[parent] = tmp;
                i = parent;
            } else {
                break;
            }
        }
    }

    HuffmanNode* pop() {
        if (count == 0) return 0;
        HuffmanNode* top = data[0];
        data[0] = data[--count];
        int i = 0;
        while (true) {
            int left = 2 * i + 1;
            int right = 2 * i + 2;
            int smallest = i;
            if (left < count && nodeLess(data[left], data[smallest])) smallest = left;
            if (right < count && nodeLess(data[right], data[smallest])) smallest = right;
            if (smallest != i) {
                HuffmanNode* tmp = data[i];
                data[i] = data[smallest];
                data[smallest] = tmp;
                i = smallest;
            } else {
                break;
            }
        }
        return top;
    }
};

class ByteBuffer {
public:
    unsigned char* ptr;
    cpp_size_t len;
    cpp_size_t cap;

    ByteBuffer() : ptr(0), len(0), cap(0) {}

    bool reserve(cpp_size_t needed) {
        if (needed <= cap) return true;
        cpp_size_t new_cap = (cap == 0) ? 1024 : cap * 2;
        while (new_cap < needed) new_cap *= 2;
        unsigned char* next = (unsigned char*)realloc(ptr, new_cap);
        if (!next) return false;
        ptr = next;
        cap = new_cap;
        return true;
    }

    bool push(unsigned char b) {
        if (!reserve(len + 1)) return false;
        ptr[len++] = b;
        return true;
    }

    bool appendU32(unsigned int val) {
        return push((unsigned char)(val & 0xFF)) &&
               push((unsigned char)((val >> 8) & 0xFF)) &&
               push((unsigned char)((val >> 16) & 0xFF)) &&
               push((unsigned char)((val >> 24) & 0xFF));
    }

    bool appendU16(unsigned short val) {
        return push((unsigned char)(val & 0xFF)) &&
               push((unsigned char)((val >> 8) & 0xFF));
    }

    void release() {
        free(ptr);
        ptr = 0;
        len = 0;
        cap = 0;
    }
};

class HuffmanCompressor {
private:
    char codes[256][260];

    HuffmanNode* buildTree(const unsigned int freqs[256]) {
        MinHeap heap;
        for (int s = 0; s < 256; s++) {
            if (freqs[s] > 0) {
                HuffmanNode* leaf = createLeaf((unsigned char)s, freqs[s]);
                if (!leaf) return 0;
                heap.push(leaf);
            }
        }
        if (heap.size() == 0) return 0;
        if (heap.size() == 1) {
            HuffmanNode* only = heap.pop();
            HuffmanNode* dummy = createLeaf(0, 0);
            return createInternal(only, dummy);
        }
        while (heap.size() > 1) {
            HuffmanNode* left = heap.pop();
            HuffmanNode* right = heap.pop();
            heap.push(createInternal(left, right));
        }
        return heap.pop();
    }

    void buildCodes(HuffmanNode* node, char* path, int depth) {
        if (!node) return;
        if (!node->left && !node->right) {
            if (depth == 0) {
                codes[node->symbol][0] = '0';
                codes[node->symbol][1] = '\0';
            } else {
                for (int i = 0; i < depth; i++) {
                    codes[node->symbol][i] = path[i];
                }
                codes[node->symbol][depth] = '\0';
            }
            return;
        }
        path[depth] = '0';
        buildCodes(node->left, path, depth + 1);
        path[depth] = '1';
        buildCodes(node->right, path, depth + 1);
    }

public:
    unsigned int compress(const unsigned char* rle_data, unsigned int rle_len, unsigned char** out_buf) {
        unsigned int freqs[256];
        for (int s = 0; s < 256; s++) {
            freqs[s] = 0;
            codes[s][0] = '\0';
        }
        for (unsigned int i = 0; i < rle_len; i++) {
            freqs[rle_data[i]]++;
        }

        unsigned short sym_count = 0;
        for (int s = 0; s < 256; s++) {
            if (freqs[s] > 0) sym_count++;
        }

        HuffmanNode* root = buildTree(freqs);
        if (!root) return 0;

        char path[260];
        buildCodes(root, path, 0);
        freeTree(root);

        ByteBuffer out;
        if (!out.appendU32(rle_len) || !out.appendU16(sym_count)) {
            out.release();
            return 0;
        }

        for (int s = 0; s < 256; s++) {
            if (freqs[s] > 0) {
                if (!out.push((unsigned char)s) || !out.appendU32(freqs[s])) {
                    out.release();
                    return 0;
                }
            }
        }

        unsigned char current_byte = 0;
        int bit_count = 0;
        for (unsigned int i = 0; i < rle_len; i++) {
            const char* code = codes[rle_data[i]];
            for (int c = 0; code[c] != '\0'; c++) {
                current_byte = (unsigned char)((current_byte << 1) | (code[c] - '0'));
                if (++bit_count == 8) {
                    if (!out.push(current_byte)) {
                        out.release();
                        return 0;
                    }
                    current_byte = 0;
                    bit_count = 0;
                }
            }
        }
        if (bit_count > 0) {
            current_byte = (unsigned char)(current_byte << (8 - bit_count));
            if (!out.push(current_byte)) {
                out.release();
                return 0;
            }
        }

        *out_buf = out.ptr;
        return (unsigned int)out.len;
    }

    unsigned int decompress(const unsigned char* comp_data, unsigned int comp_len, unsigned char** out_rle) {
        if (!comp_data || comp_len < 6) return 0;

        unsigned int rle_len = (unsigned int)comp_data[0]
                             | ((unsigned int)comp_data[1] << 8)
                             | ((unsigned int)comp_data[2] << 16)
                             | ((unsigned int)comp_data[3] << 24);
        unsigned short sym_count = (unsigned short)((unsigned short)comp_data[4] | ((unsigned short)comp_data[5] << 8));

        unsigned int offset = 6;
        if (comp_len < offset + (unsigned int)sym_count * 5) return 0;

        unsigned int freqs[256];
        for (int s = 0; s < 256; s++) freqs[s] = 0;

        for (unsigned short i = 0; i < sym_count; i++) {
            unsigned char sym = comp_data[offset];
            unsigned int f = (unsigned int)comp_data[offset + 1]
                           | ((unsigned int)comp_data[offset + 2] << 8)
                           | ((unsigned int)comp_data[offset + 3] << 16)
                           | ((unsigned int)comp_data[offset + 4] << 24);
            freqs[sym] = f;
            offset += 5;
        }

        HuffmanNode* root = buildTree(freqs);
        if (!root) return 0;

        unsigned char* rle_buf = (unsigned char*)malloc((cpp_size_t)rle_len);
        if (!rle_buf) {
            freeTree(root);
            return 0;
        }

        unsigned int written = 0;
        HuffmanNode* curr = root;
        for (unsigned int i = offset; i < comp_len && written < rle_len; i++) {
            unsigned char byte = comp_data[i];
            for (int b = 7; b >= 0 && written < rle_len; b--) {
                int bit = (byte >> b) & 1;
                curr = (bit == 0) ? curr->left : curr->right;
                if (!curr->left && !curr->right) {
                    rle_buf[written++] = curr->symbol;
                    curr = root;
                }
            }
        }
        freeTree(root);

        if (written != rle_len) {
            free(rle_buf);
            return 0;
        }

        *out_rle = rle_buf;
        return written;
    }
};

extern "C" {
    EXPORT unsigned int compress_pipeline(const unsigned char* raw_pixels, unsigned int pixel_count,
                                          unsigned char** out_compressed, unsigned int* out_rle_size) {
        if (!raw_pixels || !out_compressed || !out_rle_size || pixel_count == 0) return 0;

        unsigned char* rle_buf = 0;
        unsigned int rle_len = c_delta_rle_encode(raw_pixels, pixel_count, &rle_buf);
        if (rle_len == 0 || !rle_buf) return 0;

        *out_rle_size = rle_len;
        HuffmanCompressor engine;
        unsigned char* comp_buf = 0;
        unsigned int comp_len = engine.compress(rle_buf, rle_len, &comp_buf);
        c_free_buffer(rle_buf);

        if (comp_len == 0 || !comp_buf) return 0;
        *out_compressed = comp_buf;
        return comp_len;
    }

    EXPORT unsigned int decompress_pipeline(const unsigned char* compressed_data, unsigned int comp_len,
                                            unsigned char** out_pixels) {
        if (!compressed_data || !out_pixels || comp_len == 0) return 0;

        HuffmanCompressor engine;
        unsigned char* rle_buf = 0;
        unsigned int rle_len = engine.decompress(compressed_data, comp_len, &rle_buf);
        if (rle_len == 0 || !rle_buf) return 0;

        unsigned int pixel_len = c_delta_rle_decode(rle_buf, rle_len, out_pixels);
        free(rle_buf);
        return pixel_len;
    }

    EXPORT void free_pipeline_buffer(unsigned char* ptr) {
        free(ptr);
    }
}