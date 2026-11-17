# ImageCompressor
A project that utlises C,C++ and Python languages to compress image sizes. It takes JPG,PNG images as input and produces images in reduced size in JPG or PNG.
# Hybrid C, C++, and Python Image Compression Engine

A desktop batch image compressor built with **Python (Tkinter, Pillow, NumPy)** and a native **C / C++** shared library.

## How It Works

1. **Python (`main.py`):** Loads images (`PNG`, `JPG`, `WebP`), splits RGB channels, and manages the batch GUI.
2. **C (`delta_rle.c`):** Applies spatial delta filtering and PackBits Run-Length Encoding.
3. **C++ (`huffman_engine.cpp`):** Builds a min-heap Huffman tree and packs variable-length bit codes.
4. **Verify & Export:** Decompresses in memory to verify bit-exact accuracy, charts size reductions, and exports **PNG** or **JPG** files.

## Files

- `main.py` — GUI, batch queue (`+` / remove), compiler auto-detection, charts, and PNG/JPG export
- `delta_rle.h` / `delta_rle.c` — C delta filter and PackBits RLE encoder/decoder
- `huffman_engine.cpp` — C++ Huffman coder and DLL exports
