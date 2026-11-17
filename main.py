import ctypes
import importlib
import os
import platform
import shutil
import struct
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS = platform.system() == "Windows"
PYTHON_BITS = struct.calcsize("P") * 8


def show_fatal_error(title, message):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(title, message)
    root.destroy()
    sys.exit(1)


def ensure_python_packages():
    required = {"numpy": "numpy", "PIL": "pillow", "matplotlib": "matplotlib"}
    missing = []
    for mod_name, pip_name in required.items():
        try:
            importlib.import_module(mod_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", *missing],
                check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as err:
            show_fatal_error("Missing Python Libraries", err.stderr or str(err))


ensure_python_packages()

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageTk


def find_compiler_toolchain():
    """Locate gcc and g++ dynamically across PATH, env vars, and standard Windows directories."""
    env_cc = os.environ.get("CC")
    env_cxx = os.environ.get("CXX")
    if env_cc and env_cxx and os.path.isfile(env_cc) and os.path.isfile(env_cxx):
        return env_cc, env_cxx, os.path.dirname(env_cc)

    path_gcc = shutil.which("gcc")
    path_gpp = shutil.which("g++")
    if path_gcc and path_gpp:
        return path_gcc, path_gpp, os.path.dirname(path_gcc)

    if IS_WINDOWS:
        candidate_dirs = [
            r"C:\Program Files (x86)\Dev-Cpp\MinGW64\bin",
            r"C:\Program Files\Dev-Cpp\MinGW64\bin",
            r"C:\msys64\ucrt64\bin",
            r"C:\msys64\mingw64\bin",
            r"C:\msys64\mingw32\bin",
            r"C:\MinGW\bin",
            r"C:\TDM-GCC-64\bin",
            r"C:\TDM-GCC-32\bin",
            r"C:\Program Files\CodeBlocks\MinGW\bin",
            r"C:\Program Files (x86)\CodeBlocks\MinGW\bin",
            r"C:\Strawberry\c\bin",
        ]
        local_app = os.environ.get("LOCALAPPDATA", "")
        user_profile = os.environ.get("USERPROFILE", "")
        if local_app:
            candidate_dirs.append(os.path.join(local_app, "Programs", "mingw64", "bin"))
        if user_profile:
            candidate_dirs.append(os.path.join(user_profile, "scoop", "apps", "gcc", "current", "bin"))

        for folder in candidate_dirs:
            gcc_exe = os.path.join(folder, "gcc.exe")
            gpp_exe = os.path.join(folder, "g++.exe")
            if os.path.isfile(gcc_exe) and os.path.isfile(gpp_exe):
                return gcc_exe, gpp_exe, folder

    return None, None, None


def build_and_load_library():
    lib_name = "compressor.dll" if IS_WINDOWS else ("libcompressor.dylib" if platform.system() == "Darwin" else "libcompressor.so")
    lib_path = os.path.join(BASE_DIR, lib_name)
    obj_path = os.path.join(BASE_DIR, "delta_rle.o")
    c_src = os.path.join(BASE_DIR, "delta_rle.c")
    h_src = os.path.join(BASE_DIR, "delta_rle.h")
    cpp_src = os.path.join(BASE_DIR, "huffman_engine.cpp")

    gcc_exe, gpp_exe, compiler_bin = find_compiler_toolchain()

    if IS_WINDOWS and compiler_bin and os.path.isdir(compiler_bin):
        os.environ["PATH"] = compiler_bin + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(compiler_bin)

    needs_build = not os.path.exists(lib_path)
    if not needs_build and gcc_exe and gpp_exe:
        dll_mtime = os.path.getmtime(lib_path)
        for src in (c_src, h_src, cpp_src):
            if os.path.exists(src) and os.path.getmtime(src) > dll_mtime:
                needs_build = True
                break

    if needs_build:
        if not gcc_exe or not gpp_exe:
            show_fatal_error(
                "C/C++ Compiler Not Found",
                "Could not find 'gcc' and 'g++' in your system PATH or standard install folders.\n\n"
                "Please install MinGW-w64 / MSYS2 / Dev-C++ (Windows) or GCC/Clang (Linux/macOS), "
                "add its 'bin' folder to PATH, and run the program again."
            )

        if os.path.exists(lib_path):
            try:
                os.remove(lib_path)
            except OSError:
                pass

        try:
            if IS_WINDOWS:
                arch_flag = "-m64" if PYTHON_BITS == 64 else "-m32"
                subprocess.run(
                    [gcc_exe, arch_flag, "-std=c99", "-O3", "-c", c_src, "-o", obj_path],
                    check=True, capture_output=True, text=True
                )
                subprocess.run(
                    [gpp_exe, arch_flag, "-std=c++11", "-O3", "-shared", "-static-libgcc", "-fno-exceptions", "-fno-rtti",
                     "-o", lib_path, cpp_src, obj_path],
                    check=True, capture_output=True, text=True
                )
            else:
                subprocess.run(
                    [gcc_exe, "-std=c99", "-O3", "-fPIC", "-c", c_src, "-o", obj_path],
                    check=True, capture_output=True, text=True
                )
                subprocess.run(
                    [gpp_exe, "-std=c++11", "-O3", "-shared", "-fPIC", "-fno-exceptions", "-fno-rtti",
                     "-o", lib_path, cpp_src, obj_path],
                    check=True, capture_output=True, text=True
                )
        except subprocess.CalledProcessError as err:
            show_fatal_error("C/C++ Compilation Error", err.stderr or err.stdout or str(err))
        finally:
            if os.path.exists(obj_path):
                try:
                    os.remove(obj_path)
                except OSError:
                    pass

    try:
        loaded_lib = ctypes.CDLL(lib_path)
    except OSError as err:
        show_fatal_error("DLL Load Error", f"Could not load {lib_name}.\n\n{err}")

    loaded_lib.compress_pipeline.argtypes = [
        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)), ctypes.POINTER(ctypes.c_uint)
    ]
    loaded_lib.compress_pipeline.restype = ctypes.c_uint

    loaded_lib.decompress_pipeline.argtypes = [
        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))
    ]
    loaded_lib.decompress_pipeline.restype = ctypes.c_uint

    loaded_lib.free_pipeline_buffer.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
    return loaded_lib


lib = build_and_load_library()


def make_thumbnail(pil_img, max_w=260, max_h=210):
    ratio = min(max_w / max(pil_img.width, 1), max_h / max(pil_img.height, 1))
    new_w = max(1, int(pil_img.width * ratio))
    new_h = max(1, int(pil_img.height * ratio))
    resample = getattr(Image, "Resampling", Image).LANCZOS
    return ImageTk.PhotoImage(pil_img.resize((new_w, new_h), resample))


class CompressionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("C / C++ / Python Batch Image Compression Engine")
        self.root.geometry("960x710")
        self.root.configure(bg="#f4f6f9")

        self.current_image_paths = []
        self.batch_results = []
        self.selected_index = 0
        self.color_mode = tk.StringVar(value="RGB")
        self.quant_step = tk.IntVar(value=1)
        self.jpg_quality = tk.IntVar(value=75)

        # --- Row 1: Action Buttons ---
        action_frame = tk.Frame(root, bg="#f4f6f9", pady=10)
        action_frame.pack(fill="x", padx=20)

        tk.Button(
            action_frame, text="Select Images & Compress", command=self.select_and_compress,
            font=("Segoe UI", 10, "bold"), bg="#0d6efd", fg="white", padx=14, pady=6, relief="flat"
        ).pack(side="left", padx=(0, 8))

        self.chart_btn = tk.Button(
            action_frame, text="View Comparison Chart", command=self.show_chart,
            font=("Segoe UI", 10), bg="#198754", fg="white", padx=12, pady=6, relief="flat", state="disabled"
        )
        self.chart_btn.pack(side="left", padx=8)

        # --- Row 2: Color & Compression Mode Controls ---
        config_frame = tk.Frame(root, bg="white", pady=8, padx=14, relief="groove", bd=1)
        config_frame.pack(fill="x", padx=20, pady=(0, 6))

        tk.Label(
            config_frame, text="Color:", font=("Segoe UI", 9, "bold"), bg="white", fg="#212529"
        ).pack(side="left", padx=(0, 4))

        tk.Radiobutton(
            config_frame, text="RGB", variable=self.color_mode, value="RGB",
            command=self.reprocess_current, font=("Segoe UI", 9), bg="white", activebackground="white"
        ).pack(side="left", padx=2)

        tk.Radiobutton(
            config_frame, text="Grayscale", variable=self.color_mode, value="L",
            command=self.reprocess_current, font=("Segoe UI", 9), bg="white", activebackground="white"
        ).pack(side="left", padx=(2, 12))

        tk.Label(
            config_frame, text="C/C++ Mode:", font=("Segoe UI", 9, "bold"), bg="white", fg="#212529"
        ).pack(side="left", padx=(0, 4))

        for label, step in [("Lossless (Exact)", 1), ("High Comp (Q4)", 4), ("Max Comp (Q8)", 8)]:
            tk.Radiobutton(
                config_frame, text=label, variable=self.quant_step, value=step,
                command=self.reprocess_current, font=("Segoe UI", 9), bg="white", activebackground="white"
            ).pack(side="left", padx=3)

        self.save_jpg_btn = tk.Button(
            config_frame, text="Save JPG(s)", command=lambda: self.save_images_format("JPG"),
            font=("Segoe UI", 9, "bold"), bg="#0dcaf0", fg="#000000", padx=10, pady=4, relief="flat", state="disabled"
        )
        self.save_jpg_btn.pack(side="right", padx=(5, 0))

        self.save_png_btn = tk.Button(
            config_frame, text="Save PNG(s)", command=lambda: self.save_images_format("PNG"),
            font=("Segoe UI", 9, "bold"), bg="#20c997", fg="#000000", padx=10, pady=4, relief="flat", state="disabled"
        )
        self.save_png_btn.pack(side="right", padx=5)

        # --- Row 2B: JPEG Export Quality Slider ---
        jpg_bar = tk.Frame(root, bg="#f4f6f9")
        jpg_bar.pack(fill="x", padx=20, pady=(0, 4))

        tk.Label(
            jpg_bar, text="JPG Export Quality (lower = smaller JPG file):",
            font=("Segoe UI", 9), bg="#f4f6f9", fg="#495057"
        ).pack(side="left")

        tk.Scale(
            jpg_bar, from_=30, to=95, orient="horizontal", variable=self.jpg_quality,
            length=180, showvalue=True, bg="#f4f6f9", highlightthickness=0
        ).pack(side="left", padx=8)

        # --- Row 3: File Queue Listbox (+ / Remove) + Side-by-Side Preview ---
        middle_frame = tk.Frame(root, bg="#f4f6f9")
        middle_frame.pack(fill="x", padx=20, pady=4)

        list_container = tk.Frame(middle_frame, bg="white", relief="groove", bd=1)
        list_container.pack(side="left", fill="y", padx=(0, 12))

        list_header = tk.Frame(list_container, bg="#e9ecef")
        list_header.pack(fill="x")

        tk.Label(
            list_header, text="Files (Click to Inspect)",
            font=("Segoe UI", 9, "bold"), bg="#e9ecef", fg="#212529", pady=4, padx=8
        ).pack(side="left")

        self.add_more_btn = tk.Button(
            list_header, text="+", command=self.add_more_files,
            font=("Segoe UI", 10, "bold"), bg="#198754", fg="white",
            width=3, relief="flat", cursor="hand2"
        )
        self.add_more_btn.pack(side="right", padx=3, pady=2)

        list_body = tk.Frame(list_container, bg="white")
        list_body.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_body, orient="vertical")
        self.file_listbox = tk.Listbox(
            list_body, width=30, height=11, font=("Segoe UI", 9),
            selectmode=tk.EXTENDED,
            yscrollcommand=scrollbar.set, selectbackground="#0d6efd", selectforeground="white",
            borderwidth=0, highlightthickness=0
        )
        scrollbar.config(command=self.file_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.file_listbox.pack(side="left", fill="both", expand=True)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.file_listbox.bind("<Delete>", lambda e: self.remove_selected_files())

        list_footer = tk.Frame(list_container, bg="#f8f9fa", pady=4, padx=6)
        list_footer.pack(fill="x")

        self.remove_btn = tk.Button(
            list_footer, text="Remove Selected", command=self.remove_selected_files,
            font=("Segoe UI", 8, "bold"), bg="#dc3545", fg="white",
            padx=8, pady=2, relief="flat", state="disabled"
        )
        self.remove_btn.pack(fill="x")

        preview_container = tk.Frame(middle_frame, bg="#f4f6f9")
        preview_container.pack(side="left", expand=True)

        self.orig_panel = tk.Label(preview_container, text="Input Preview", bg="#e9ecef", width=36, height=13)
        self.orig_panel.grid(row=0, column=0, padx=10)

        self.recon_panel = tk.Label(preview_container, text="Decompressed Preview", bg="#e9ecef", width=36, height=13)
        self.recon_panel.grid(row=0, column=1, padx=10)

        self.orig_caption = tk.Label(preview_container, text="Input Image (Python / Pillow)", bg="#f4f6f9", font=("Segoe UI", 9, "bold"))
        self.orig_caption.grid(row=1, column=0, pady=4)

        self.recon_caption = tk.Label(preview_container, text="Reconstructed After C++ & C Pipeline", bg="#f4f6f9", font=("Segoe UI", 9, "bold"))
        self.recon_caption.grid(row=1, column=1, pady=4)

        # --- Row 4: Benchmark & Batch Summary Report ---
        self.stats_label = tk.Label(
            root, text="Click 'Select Images & Compress' or '+' on the file list to add one or more images.",
            font=("Consolas", 10), bg="white", fg="#212529", justify="left",
            padx=18, pady=12, relief="groove", width=102
        )
        self.stats_label.pack(pady=8, padx=20)

    def _compress_single_path(self, file_path, mode, q_step):
        disk_bytes = os.path.getsize(file_path)
        img = Image.open(file_path).convert(mode)
        raw_arr = np.array(img, dtype=np.uint8)

        if mode == "RGB":
            channels = 3
            flat_pixels = np.ascontiguousarray(raw_arr.transpose(2, 0, 1)).flatten()
            mode_label = "RGB (3 Ch)"
        else:
            channels = 1
            flat_pixels = np.ascontiguousarray(raw_arr.flatten())
            mode_label = "Grayscale (1 Ch)"

        if q_step > 1:
            proc_pixels = np.ascontiguousarray(((flat_pixels // q_step) * q_step).astype(np.uint8))
        else:
            proc_pixels = flat_pixels

        num_bytes = proc_pixels.size
        raw_ptr = proc_pixels.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte))
        comp_ptr = ctypes.POINTER(ctypes.c_ubyte)()
        rle_size = ctypes.c_uint()

        t0 = time.perf_counter()
        comp_size = lib.compress_pipeline(raw_ptr, num_bytes, ctypes.byref(comp_ptr), ctypes.byref(rle_size))
        t_comp = (time.perf_counter() - t0) * 1000

        if comp_size == 0:
            raise RuntimeError(f"Compression returned 0 bytes for {os.path.basename(file_path)}.")

        decomp_ptr = ctypes.POINTER(ctypes.c_ubyte)()
        t1 = time.perf_counter()
        decomp_size = lib.decompress_pipeline(comp_ptr, comp_size, ctypes.byref(decomp_ptr))
        t_decomp = (time.perf_counter() - t1) * 1000

        reconstructed_flat = np.ctypeslib.as_array(decomp_ptr, shape=(decomp_size,)).copy()
        is_exact = np.array_equal(proc_pixels, reconstructed_flat)

        lib.free_pipeline_buffer(comp_ptr)
        lib.free_pipeline_buffer(decomp_ptr)

        if channels == 3:
            recon_arr = reconstructed_flat.reshape((3, img.height, img.width)).transpose(1, 2, 0)
            recon_img = Image.fromarray(recon_arr, mode="RGB")
        else:
            recon_arr = reconstructed_flat.reshape((img.height, img.width))
            recon_img = Image.fromarray(recon_arr, mode="L")

        raw_reduction = (1 - (comp_size / num_bytes)) * 100

        return {
            "path": file_path,
            "name": os.path.basename(file_path),
            "stem": os.path.splitext(os.path.basename(file_path))[0],
            "width": img.width,
            "height": img.height,
            "mode": mode,
            "mode_label": mode_label,
            "q_step": q_step,
            "orig_img": img,
            "recon_img": recon_img,
            "disk_bytes": disk_bytes,
            "raw_bytes": num_bytes,
            "rle_bytes": rle_size.value,
            "comp_bytes": comp_size,
            "reduction": raw_reduction,
            "t_comp": t_comp,
            "t_decomp": t_decomp,
            "is_lossless": is_exact,
        }

    def reprocess_current(self):
        if self.current_image_paths:
            self.process_batch_images(self.current_image_paths)

    def select_and_compress(self):
        file_paths = filedialog.askopenfilenames(
            title="Choose One or Multiple Images",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.webp")]
        )
        if not file_paths:
            return
        self.current_image_paths = list(file_paths)
        self.process_batch_images(self.current_image_paths)

    def add_more_files(self):
        file_paths = filedialog.askopenfilenames(
            title="Add One or More Images to List",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.webp")]
        )
        if not file_paths:
            return

        mode = self.color_mode.get()
        q_step = self.quant_step.get()
        start_idx = len(self.batch_results)

        try:
            for fp in file_paths:
                res = self._compress_single_path(fp, mode, q_step)
                self.current_image_paths.append(fp)
                self.batch_results.append(res)

            self.populate_listbox(select_idx=start_idx)
            self.display_item(start_idx)
            self._update_action_states()
        except Exception as e:
            messagebox.showerror("Add Files Error", str(e))

    def remove_selected_files(self):
        selection = self.file_listbox.curselection()
        if not selection or not self.batch_results:
            return

        to_remove = sorted(selection, reverse=True)
        first_removed = min(to_remove)

        for idx in to_remove:
            if 0 <= idx < len(self.batch_results):
                self.batch_results.pop(idx)
            if 0 <= idx < len(self.current_image_paths):
                self.current_image_paths.pop(idx)

        if not self.batch_results:
            self.file_listbox.delete(0, tk.END)
            self.orig_panel.configure(image="", width=36, height=13, text="Input Preview")
            self.orig_panel.image = None
            self.recon_panel.configure(image="", width=36, height=13, text="Decompressed Preview")
            self.recon_panel.image = None
            self.orig_caption.configure(text="Input Image (Python / Pillow)")
            self.recon_caption.configure(text="Reconstructed After C++ & C Pipeline")
            self.stats_label.configure(
                text="All files removed. Click 'Select Images & Compress' or '+' to add images."
            )
            self._update_action_states()
            return

        next_idx = min(first_removed, len(self.batch_results) - 1)
        self.populate_listbox(select_idx=next_idx)
        self.display_item(next_idx)
        self._update_action_states()

    def process_batch_images(self, file_paths):
        results = []
        mode = self.color_mode.get()
        q_step = self.quant_step.get()

        try:
            for file_path in file_paths:
                results.append(self._compress_single_path(file_path, mode, q_step))

            self.batch_results = results
            self.populate_listbox(select_idx=0)
            self.display_item(0)
            self._update_action_states()
        except Exception as e:
            messagebox.showerror("Batch Processing Error", str(e))

    def _update_action_states(self):
        has_items = len(self.batch_results) > 0
        state = "normal" if has_items else "disabled"
        self.chart_btn.configure(state=state)
        self.save_png_btn.configure(state=state)
        self.save_jpg_btn.configure(state=state)
        self.remove_btn.configure(state=state)

    def populate_listbox(self, select_idx=0):
        self.file_listbox.delete(0, tk.END)
        for idx, item in enumerate(self.batch_results):
            self.file_listbox.insert(tk.END, f"{idx + 1}. {item['name']} ({item['reduction']:.1f}%)")
        if self.batch_results and 0 <= select_idx < len(self.batch_results):
            self.file_listbox.selection_set(select_idx)
            self.file_listbox.see(select_idx)

    def on_listbox_select(self, event):
        selection = self.file_listbox.curselection()
        if selection:
            self.display_item(selection[0])

    def display_item(self, idx):
        if not (0 <= idx < len(self.batch_results)):
            return
        self.selected_index = idx
        item = self.batch_results[idx]

        orig_thumb = make_thumbnail(item["orig_img"])
        recon_thumb = make_thumbnail(item["recon_img"])

        self.orig_panel.configure(image=orig_thumb, width=260, height=210, text="")
        self.orig_panel.image = orig_thumb
        self.orig_caption.configure(text=f"Input ({item['mode_label']})")

        self.recon_panel.configure(image=recon_thumb, width=260, height=210, text="")
        self.recon_panel.image = recon_thumb
        q_label = "Lossless" if item["q_step"] == 1 else f"Quantized Q{item['q_step']}"
        self.recon_caption.configure(text=f"Reconstructed ({q_label})")

        total_files = len(self.batch_results)
        tot_raw = sum(r["raw_bytes"] for r in self.batch_results)
        tot_comp = sum(r["comp_bytes"] for r in self.batch_results)
        tot_red = (1 - (tot_comp / max(tot_raw, 1))) * 100
        tot_time = sum(r["t_comp"] + r["t_decomp"] for r in self.batch_results)

        batch_line = ""
        if total_files > 1:
            batch_line = (
                f"BATCH TOTAL ({total_files} files) : Raw {tot_raw:,} B -> C/C++ Compressed {tot_comp:,} B "
                f"({tot_red:.2f}% vs raw) | Time: {tot_time:.1f} ms\n"
                f"{'-' * 92}\n"
            )

        disk_str = f" | Input Disk File: {item['disk_bytes']:,} B" if item["disk_bytes"] > 0 else ""
        report = (
            f"{batch_line}"
            f"Selected [{idx + 1}/{total_files}]   : {item['name']} ({item['width']} x {item['height']}) | {item['mode_label']}{disk_str}\n"
            f"1. Decoded Raw Grid: {item['raw_bytes']:,} bytes (uncompressed pixel matrix in memory)\n"
            f"2. C (Delta+PackRLE): {item['rle_bytes']:,} bytes\n"
            f"3. C++ (Huffman)   : {item['comp_bytes']:,} bytes  ({item['reduction']:.2f}% reduction vs raw pixels)\n"
            f"Speed & Integrity  : Compress {item['t_comp']:.2f} ms | Decompress {item['t_decomp']:.2f} ms | "
            f"{'PASSED (Bit-Exact)' if item['is_lossless'] else 'FAILED'}"
        )
        self.stats_label.configure(text=report)

    def save_images_format(self, fmt):
        if not self.batch_results:
            return

        ext = ".jpg" if fmt == "JPG" else ".png"
        q_val = self.jpg_quality.get()

        if len(self.batch_results) == 1:
            item = self.batch_results[0]
            save_path = filedialog.asksaveasfilename(
                title=f"Save Image as {fmt}",
                initialfile=f"{item['stem']}_compressed{ext}",
                filetypes=[(f"{fmt} Image", f"*{ext}")]
            )
            if not save_path:
                return
            if not save_path.lower().endswith((".jpg", ".jpeg", ".png")):
                save_path += ext
            try:
                self._write_pil_image(item["recon_img"], save_path, fmt, q_val)
                saved_kb = os.path.getsize(save_path) / 1024
                messagebox.showinfo(f"{fmt} Saved", f"Saved successfully:\n{save_path}\n\nFile Size: {saved_kb:.1f} KB")
            except Exception as e:
                messagebox.showerror("Save Error", str(e))
            return

        out_dir = filedialog.askdirectory(title=f"Select Folder to Save All {len(self.batch_results)} {fmt} Images")
        if not out_dir:
            return

        try:
            total_kb = 0.0
            for idx, item in enumerate(self.batch_results, start=1):
                out_path = os.path.join(out_dir, f"{idx:02d}_{item['stem']}_compressed{ext}")
                self._write_pil_image(item["recon_img"], out_path, fmt, q_val)
                total_kb += os.path.getsize(out_path) / 1024

            messagebox.showinfo(
                f"Batch {fmt} Save Complete",
                f"Saved {len(self.batch_results)} {fmt} images to:\n{out_dir}\n\nTotal Disk Size: {total_kb:.1f} KB"
            )
        except Exception as e:
            messagebox.showerror("Batch Save Error", str(e))

    @staticmethod
    def _write_pil_image(pil_img, path, fmt, jpg_q):
        if fmt == "JPG":
            img_to_save = pil_img if pil_img.mode in ("RGB", "L") else pil_img.convert("RGB")
            img_to_save.save(path, format="JPEG", quality=jpg_q, optimize=True, subsampling=2)
        else:
            pil_img.save(path, format="PNG", compress_level=9, optimize=True)

    def show_chart(self):
        if not self.batch_results:
            return

        plt.close("all")

        if len(self.batch_results) == 1:
            item = self.batch_results[0]
            stages = ["Decoded Raw\n(Memory)", "Delta + PackRLE\n(C Layer)", "Huffman Bitstream\n(C++ Layer)"]
            sizes_kb = [item["raw_bytes"] / 1024, item["rle_bytes"] / 1024, item["comp_bytes"] / 1024]
            colors = ["#6c757d", "#0d6efd", "#198754"]

            plt.figure(figsize=(7.5, 4.2))
            bars = plt.bar(stages, sizes_kb, color=colors, width=0.45)
            plt.ylabel("Size (KB)")
            plt.title(f"{item['name']} - {item['mode_label']} ({item['reduction']:.1f}% vs Raw)")
            for bar, sz in zip(bars, sizes_kb):
                plt.text(bar.get_x() + bar.get_width() / 2, sz + max(sizes_kb) * 0.02,
                         f"{sz:.1f} KB", ha="center", fontweight="bold")
            plt.tight_layout()
            plt.show(block=False)
            return

        names = [r["name"][:14] + ("…" if len(r["name"]) > 14 else "") for r in self.batch_results]
        raw_kb = [r["raw_bytes"] / 1024 for r in self.batch_results]
        comp_kb = [r["comp_bytes"] / 1024 for r in self.batch_results]

        x = np.arange(len(names))
        width = 0.36

        plt.figure(figsize=(max(7.5, len(names) * 1.3), 4.5))
        plt.bar(x - width / 2, raw_kb, width, label="Decoded Raw (KB)", color="#6c757d")
        plt.bar(x + width / 2, comp_kb, width, label="Compressed C/C++ (KB)", color="#198754")

        plt.xticks(x, names, rotation=20, ha="right")
        plt.ylabel("Size (KB)")
        tot_red = (1 - (sum(comp_kb) / max(sum(raw_kb), 1e-6))) * 100
        plt.title(f"Batch Compression Comparison ({len(names)} Files | {tot_red:.1f}% vs Raw)")
        plt.legend()
        plt.tight_layout()
        plt.show(block=False)


if __name__ == "__main__":
    root = tk.Tk()
    app = CompressionApp(root)
    root.mainloop()